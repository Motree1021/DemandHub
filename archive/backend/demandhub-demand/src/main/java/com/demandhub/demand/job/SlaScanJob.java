package com.demandhub.demand.job;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.SlaConfigEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import com.demandhub.demand.mapper.SlaConfigMapper;
import com.demandhub.demand.mq.DemandEventMessage;
import com.demandhub.demand.mq.MqTopics;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * SLA 超时扫描定时任务（FR-M7 / 架构 4.5）：
 * 按 类型 × 状态 配置的停留阈值扫描在途需求——
 * 超过预警阈值发黄色预警，超过最长停留发红色告警（通知经理 + 需求管理者）。
 * 去重：Redis 标记每次停留每级仅告警一次（需求离开该状态后再次进入重新计）。
 */
@Slf4j
@Component
public class SlaScanJob {

    /** 告警去重标记 TTL（覆盖一次完整停留周期即可） */
    private static final Duration ALERT_MARK_TTL = Duration.ofDays(7);

    private final SlaConfigMapper slaConfigMapper;
    private final DemandMapper demandMapper;
    private final DemandTransitionLogMapper transitionLogMapper;
    private final RocketMQTemplate rocketMQTemplate;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SlaScanJob(SlaConfigMapper slaConfigMapper, DemandMapper demandMapper,
                      DemandTransitionLogMapper transitionLogMapper,
                      RocketMQTemplate rocketMQTemplate, StringRedisTemplate redis) {
        this.slaConfigMapper = slaConfigMapper;
        this.demandMapper = demandMapper;
        this.transitionLogMapper = transitionLogMapper;
        this.rocketMQTemplate = rocketMQTemplate;
        this.redis = redis;
    }

    @Scheduled(fixedDelayString = "${demandhub.sla.scan-interval-ms:30000}", initialDelay = 20000)
    public void scan() {
        List<SlaConfigEntity> configs = slaConfigMapper.selectList(
                new LambdaQueryWrapper<SlaConfigEntity>().eq(SlaConfigEntity::getEnabled, 1));
        for (SlaConfigEntity config : configs) {
            try {
                scanConfig(config);
            } catch (Exception e) {
                log.error("[SlaScanJob] 扫描失败 {}/{}: {}", config.getDemandTypeCode(), config.getStatus(), e.getMessage());
            }
        }
    }

    private void scanConfig(SlaConfigEntity config) {
        List<DemandEntity> demands = demandMapper.selectList(new LambdaQueryWrapper<DemandEntity>()
                .eq(DemandEntity::getDemandTypeCode, config.getDemandTypeCode())
                .eq(DemandEntity::getStatus, config.getStatus())
                .eq(DemandEntity::getOnHold, 0));
        if (demands.isEmpty()) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        for (DemandEntity demand : demands) {
            LocalDateTime enteredAt = enteredAt(demand);
            if (enteredAt == null) {
                continue;
            }
            long elapsedMinutes = Duration.between(enteredAt, now).toMinutes();
            if (elapsedMinutes >= config.getMaxMinutes()) {
                fireAlert(demand, config, "RED", elapsedMinutes);
            } else if (elapsedMinutes >= config.getWarnMinutes()) {
                fireAlert(demand, config, "YELLOW", elapsedMinutes);
            }
        }
    }

    /** 当前状态的进入时刻：最近一次流转日志中 to_status=当前状态的时间；兜底提交时间 */
    private LocalDateTime enteredAt(DemandEntity demand) {
        DemandTransitionLogEntity last = transitionLogMapper.selectOne(new LambdaQueryWrapper<DemandTransitionLogEntity>()
                .eq(DemandTransitionLogEntity::getDemandId, demand.getId())
                .eq(DemandTransitionLogEntity::getToStatus, demand.getStatus())
                .orderByDesc(DemandTransitionLogEntity::getId)
                .last("LIMIT 1"));
        if (last != null && last.getCreatedAt() != null) {
            return last.getCreatedAt();
        }
        return demand.getSubmittedAt() != null ? demand.getSubmittedAt() : demand.getCreatedAt();
    }

    private void fireAlert(DemandEntity demand, SlaConfigEntity config, String level, long elapsedMinutes) {
        String markKey = "sla:alert:" + level + ":" + demand.getId() + ":" + demand.getStatus();
        Boolean first = redis.opsForValue().setIfAbsent(markKey, "1", ALERT_MARK_TTL);
        if (!Boolean.TRUE.equals(first)) {
            return;
        }
        try {
            DemandEventMessage message = new DemandEventMessage();
            message.setDemandId(demand.getId());
            message.setDemandNo(demand.getDemandNo());
            message.setEvent("SLA_ALERT");
            message.setFromStatus(demand.getStatus());
            message.setToStatus(demand.getStatus());
            message.setOperatorId(0L);
            message.setTitle(demand.getTitle());
            message.setDemandTypeCode(demand.getDemandTypeCode());
            message.setSubmitterId(demand.getSubmitterId());
            message.setActualDemanderId(demand.getActualDemanderId());
            message.setAssigneeOrgId(demand.getAssigneeOrgId());
            message.setAssigneeUserId(demand.getAssigneeUserId());
            Map<String, Object> extra = new HashMap<>();
            extra.put("level", level);
            extra.put("levelText", "RED".equals(level) ? "红色告警（已超时）" : "黄色预警（即将超时）");
            extra.put("elapsedMinutes", elapsedMinutes);
            extra.put("warnMinutes", config.getWarnMinutes());
            extra.put("maxMinutes", config.getMaxMinutes());
            message.setExtra(extra);
            rocketMQTemplate.syncSend(MqTopics.DEMAND_EVENT_TOPIC,
                    MessageBuilder.withPayload(objectMapper.writeValueAsString(message)).build());
            log.info("[SlaScanJob] SLA {} 告警已发送: {} 在 {} 停留 {} 分钟", level, demand.getDemandNo(), demand.getStatus(), elapsedMinutes);
        } catch (Exception e) {
            // 发送失败删除去重标记，下轮重试
            redis.delete(markKey);
            log.error("[SlaScanJob] SLA 告警发送失败: {}: {}", demand.getDemandNo(), e.getMessage());
        }
    }
}

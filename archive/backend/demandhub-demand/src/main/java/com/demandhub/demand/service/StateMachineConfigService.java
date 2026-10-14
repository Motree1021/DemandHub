package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.StateMachineConfigEntity;
import com.demandhub.demand.mapper.StateMachineConfigMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStatus;
import com.demandhub.demand.statemachine.StateMachineConfig;
import com.demandhub.demand.statemachine.TransitionRule;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * M8 状态机配置管理（FR-M8-02）：DB JSON 配置 + 校验 + 热加载（不重启即时生效）。
 * 加载策略：启动时加载 + 定时兜底刷新 + 管理端变更后立即刷新；解析失败的配置跳过并告警，保留上一份可用配置。
 */
@Slf4j
@Service
public class StateMachineConfigService {

    private static final Set<String> VALID_ROLES = Set.of("ADMIN", "EXECUTIVE", "MANAGER", "HANDLER");

    private final StateMachineConfigMapper configMapper;
    private final StateMachineConfig stateMachineConfig;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public StateMachineConfigService(StateMachineConfigMapper configMapper, StateMachineConfig stateMachineConfig) {
        this.configMapper = configMapper;
        this.stateMachineConfig = stateMachineConfig;
    }

    @PostConstruct
    public void loadOnStartup() {
        refreshFromDb();
    }

    /** 定时兜底刷新（多实例/直连改库场景）；管理端变更后调用本方法即时生效 */
    @Scheduled(fixedDelay = 30000, initialDelay = 30000)
    public synchronized void refreshFromDb() {
        List<StateMachineConfigEntity> configs = configMapper.selectList(
                new LambdaQueryWrapper<StateMachineConfigEntity>().eq(StateMachineConfigEntity::getStatus, "ACTIVE"));
        Map<String, List<TransitionRule>> tables = new HashMap<>();
        for (StateMachineConfigEntity config : configs) {
            try {
                tables.put(config.getConfigKey(), parseRules(config.getConfigJson()));
            } catch (BizException e) {
                log.error("[StateMachine] 配置 {} 解析失败，跳过（保留上一份可用配置）: {}", config.getConfigKey(), e.getMessage());
            }
        }
        stateMachineConfig.refreshDbTables(tables);
    }

    public List<StateMachineConfigEntity> list() {
        return configMapper.selectList(new LambdaQueryWrapper<StateMachineConfigEntity>().orderByAsc(StateMachineConfigEntity::getId));
    }

    public StateMachineConfigEntity requireById(Long id) {
        StateMachineConfigEntity entity = configMapper.selectById(id);
        if (entity == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "状态机配置不存在: " + id);
        }
        return entity;
    }

    public StateMachineConfigEntity create(StateMachineConfigEntity request) {
        validate(request.getConfigJson());
        if (!StringUtils.hasText(request.getConfigKey())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "配置标识不能为空");
        }
        StateMachineConfigEntity existing = configMapper.selectOne(new LambdaQueryWrapper<StateMachineConfigEntity>()
                .eq(StateMachineConfigEntity::getConfigKey, request.getConfigKey()));
        if (existing != null) {
            throw new BizException(ErrorCode.BIZ_ERROR, "配置标识已存在: " + request.getConfigKey());
        }
        if (!StringUtils.hasText(request.getStatus())) {
            request.setStatus("ACTIVE");
        }
        request.setId(null);
        configMapper.insert(request);
        refreshFromDb();
        return request;
    }

    public StateMachineConfigEntity update(Long id, StateMachineConfigEntity request) {
        StateMachineConfigEntity entity = requireById(id);
        if (StringUtils.hasText(request.getConfigJson()) && !request.getConfigJson().equals(entity.getConfigJson())) {
            validate(request.getConfigJson());
            entity.setConfigJson(request.getConfigJson());
        }
        if (StringUtils.hasText(request.getConfigName())) {
            entity.setConfigName(request.getConfigName());
        }
        if (StringUtils.hasText(request.getStatus())) {
            entity.setStatus(request.getStatus());
        }
        if (request.getRemark() != null) {
            entity.setRemark(request.getRemark());
        }
        configMapper.updateById(entity);
        refreshFromDb();
        return entity;
    }

    /** 导出当前生效的 DEFAULT 流转表 JSON（新建配置的起点模板） */
    public String exportDefaultJson() {
        try {
            List<Map<String, Object>> rules = new ArrayList<>();
            for (TransitionRule rule : stateMachineConfig.rules(StateMachineConfig.DEFAULT_KEY)) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("from", rule.from().name());
                item.put("event", rule.event().name());
                item.put("to", rule.to() == null ? null : rule.to().name());
                item.put("roles", rule.roles());
                item.put("remark", rule.remark());
                rules.add(item);
            }
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(Map.of("rules", rules));
        } catch (Exception e) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "导出默认配置失败: " + e.getMessage());
        }
    }

    /** 校验配置 JSON 合法性（保存前调用），不合法抛 {@link ErrorCode#STATE_MACHINE_CONFIG_INVALID} */
    public void validate(String configJson) {
        parseRules(configJson);
    }

    private List<TransitionRule> parseRules(String configJson) {
        if (!StringUtils.hasText(configJson)) {
            throw new BizException(ErrorCode.STATE_MACHINE_CONFIG_INVALID, "配置 JSON 不能为空");
        }
        JsonNode root;
        try {
            root = objectMapper.readTree(configJson);
        } catch (Exception e) {
            throw new BizException(ErrorCode.STATE_MACHINE_CONFIG_INVALID, "JSON 解析失败: " + e.getMessage());
        }
        JsonNode rulesNode = root.get("rules");
        if (rulesNode == null || !rulesNode.isArray() || rulesNode.isEmpty()) {
            throw new BizException(ErrorCode.STATE_MACHINE_CONFIG_INVALID, "缺少 rules 数组或为空");
        }
        List<TransitionRule> rules = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        int index = 0;
        for (JsonNode node : rulesNode) {
            index++;
            String from = text(node, "from");
            String event = text(node, "event");
            String to = text(node, "to");
            String remark = text(node, "remark");
            DemandStatus fromStatus = parseEnum(DemandStatus.class, from, "from", index, errors);
            DemandEvent demandEvent = parseEnum(DemandEvent.class, event, "event", index, errors);
            DemandStatus toStatus = to == null ? null : parseEnum(DemandStatus.class, to, "to", index, errors);
            Set<String> roles = new HashSet<>();
            JsonNode rolesNode = node.get("roles");
            if (rolesNode != null && rolesNode.isArray()) {
                for (JsonNode r : rolesNode) {
                    String role = r.asText();
                    if (!VALID_ROLES.contains(role)) {
                        errors.add("第" + index + "条 roles 含非法角色: " + role);
                    } else {
                        roles.add(role);
                    }
                }
            }
            if (fromStatus != null && demandEvent != null) {
                rules.add(new TransitionRule(fromStatus, demandEvent, toStatus, roles, remark));
            }
        }
        if (!errors.isEmpty()) {
            throw new BizException(ErrorCode.STATE_MACHINE_CONFIG_INVALID, String.join("；", errors));
        }
        return rules;
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    private <E extends Enum<E>> E parseEnum(Class<E> type, String value, String field, int index, List<String> errors) {
        if (value == null) {
            errors.add("第" + index + "条缺少 " + field);
            return null;
        }
        try {
            return Enum.valueOf(type, value);
        } catch (IllegalArgumentException e) {
            errors.add("第" + index + "条 " + field + " 非法: " + value);
            return null;
        }
    }
}

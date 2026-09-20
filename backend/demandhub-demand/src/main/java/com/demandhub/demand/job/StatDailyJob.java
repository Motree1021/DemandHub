package com.demandhub.demand.job;

import com.demandhub.demand.mapper.DemandStatDailyMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 看板预聚合定时任务骨架（架构 4.6）：每 5 分钟把 demand 当前快照按
 * 日 × 类型 × 承接组织 × 提报组织 × 状态 汇总刷新进 demand_stat_daily。
 * 一期只做表结构 + 增量刷新骨架，看板查询接口在 M6 阶段落地。
 */
@Slf4j
@Component
public class StatDailyJob {

    private final DemandStatDailyMapper statDailyMapper;

    public StatDailyJob(DemandStatDailyMapper statDailyMapper) {
        this.statDailyMapper = statDailyMapper;
    }

    @Scheduled(cron = "${demandhub.stat.refresh-cron:0 */5 * * * ?}")
    public void refresh() {
        try {
            int rows = statDailyMapper.refreshTodaySnapshot();
            log.debug("[StatDailyJob] 预聚合刷新完成，影响 {} 行", rows);
        } catch (Exception e) {
            log.error("[StatDailyJob] 预聚合刷新失败: {}", e.getMessage());
        }
    }
}

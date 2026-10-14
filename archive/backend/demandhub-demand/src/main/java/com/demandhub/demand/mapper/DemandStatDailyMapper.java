package com.demandhub.demand.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.demand.entity.DemandStatDailyEntity;
import org.apache.ibatis.annotations.Insert;

public interface DemandStatDailyMapper extends BaseMapper<DemandStatDailyEntity> {

    /**
     * 当日快照聚合刷新（架构 4.6）：按 类型 × 承接组织 × 提报组织 × 状态 汇总；
     * 已关闭需求顺带累计平均周期（小时）。uk_dim 冲突即更新，幂等。
     */
    @Insert("""
            INSERT INTO demand_stat_daily(stat_date, demand_type_code, assignee_org_id, reporter_org_id, status, cnt, avg_cycle_hours)
            SELECT CURDATE(),
                   demand_type_code,
                   IFNULL(assignee_org_id, 0),
                   IFNULL(submitter_org_id, 0),
                   status,
                   COUNT(*),
                   AVG(CASE WHEN closed_at IS NOT NULL AND submitted_at IS NOT NULL
                            THEN TIMESTAMPDIFF(MINUTE, submitted_at, closed_at) / 60 END)
            FROM demand
            WHERE is_deleted = 0
            GROUP BY demand_type_code, IFNULL(assignee_org_id, 0), IFNULL(submitter_org_id, 0), status
            ON DUPLICATE KEY UPDATE cnt = VALUES(cnt), avg_cycle_hours = VALUES(avg_cycle_hours)
            """)
    int refreshTodaySnapshot();
}

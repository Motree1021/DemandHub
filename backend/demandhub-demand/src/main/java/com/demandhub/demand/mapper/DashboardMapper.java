package com.demandhub.demand.mapper;

import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 看板聚合查询（FR-M6-01/02）。
 * 均为 demand 表简单查询，DataScopeInterceptor 自动按登录人追加数据范围
 * （EXECUTIVE 全线 bypass；MANAGER/HANDLER 授权子树），与列表页口径一致。
 */
public interface DashboardMapper {

    /** 新增数（按提交时间区间，[from, to)） */
    @Select("SELECT COUNT(*) FROM demand WHERE is_deleted = 0 AND submitted_at >= #{from} AND submitted_at < #{to}")
    long countNewBetween(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 当前在途数（非终态） */
    @Select("SELECT COUNT(*) FROM demand WHERE is_deleted = 0 AND status NOT IN ('DONE','CLOSED')")
    long countInflight();

    /** 完成数（按关闭时间区间，[from, to)） */
    @Select("SELECT COUNT(*) FROM demand WHERE is_deleted = 0 AND status = 'DONE' AND closed_at >= #{from} AND closed_at < #{to}")
    long countDoneBetween(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 平均交付周期（小时）：DONE 在 [from,to) 关闭的 submitted→closed 均值 */
    @Select("SELECT AVG(TIMESTAMPDIFF(MINUTE, submitted_at, closed_at) / 60) FROM demand "
            + "WHERE is_deleted = 0 AND status = 'DONE' AND submitted_at IS NOT NULL AND closed_at >= #{from} AND closed_at < #{to}")
    BigDecimal avgCycleHoursBetween(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 近 12 周新增趋势：YEARWEEK(x,1) = ISO 周桶（周一始），Java 侧按 IsoFields 对齐 */
    @Select("SELECT YEARWEEK(submitted_at, 1) AS bucket, COUNT(*) AS cnt FROM demand "
            + "WHERE is_deleted = 0 AND submitted_at >= #{from} GROUP BY YEARWEEK(submitted_at, 1)")
    List<Map<String, Object>> countNewByWeek(@Param("from") LocalDateTime from);

    /** 近 12 周完成趋势（DONE 按关闭时间） */
    @Select("SELECT YEARWEEK(closed_at, 1) AS bucket, COUNT(*) AS cnt FROM demand "
            + "WHERE is_deleted = 0 AND status = 'DONE' AND closed_at >= #{from} GROUP BY YEARWEEK(closed_at, 1)")
    List<Map<String, Object>> countDoneByWeek(@Param("from") LocalDateTime from);

    /** 类型分布（按提交时间区间） */
    @Select("SELECT demand_type_code AS typeCode, COUNT(*) AS cnt FROM demand "
            + "WHERE is_deleted = 0 AND submitted_at >= #{from} AND submitted_at < #{to} GROUP BY demand_type_code ORDER BY cnt DESC")
    List<Map<String, Object>> countByType(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 渠道来源分布（按提交时间区间，FR 来源统计：CHUANGJIN_LS 显示为"创金零售"） */
    @Select("SELECT channel, COUNT(*) AS cnt FROM demand "
            + "WHERE is_deleted = 0 AND submitted_at >= #{from} AND submitted_at < #{to} GROUP BY channel ORDER BY cnt DESC")
    List<Map<String, Object>> countByChannel(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 渠道名映射（demand_channel 注册表，无数据权限过滤；未注册渠道码回退原样展示） */
    @Select("SELECT channel_code AS channelCode, channel_name AS channelName FROM demand_channel")
    List<Map<String, Object>> listChannelNames();

    /** 组织积压 Top N（当前在途按承接组织） */
    @Select("SELECT assignee_org_id AS orgId, COUNT(*) AS cnt FROM demand "
            + "WHERE is_deleted = 0 AND status NOT IN ('DONE','CLOSED') AND assignee_org_id IS NOT NULL "
            + "GROUP BY assignee_org_id ORDER BY cnt DESC LIMIT #{limit}")
    List<Map<String, Object>> topBacklogOrgs(@Param("limit") int limit);

    /** 状态分布计数（经理看板用，当前快照按状态分组） */
    @Select("SELECT status, COUNT(*) AS cnt FROM demand WHERE is_deleted = 0 GROUP BY status")
    List<Map<String, Object>> countGroupByStatus();

    /** 成员在途工作量（按当前处理人分组） */
    @Select("SELECT assignee_user_id AS userId, COUNT(*) AS inflightCnt FROM demand "
            + "WHERE is_deleted = 0 AND status NOT IN ('DONE','CLOSED') AND assignee_user_id IS NOT NULL "
            + "GROUP BY assignee_user_id ORDER BY inflightCnt DESC")
    List<Map<String, Object>> countInflightByUser();

    /** 成员工时汇总（effort_log join demand；FROM 非 demand 表，拦截器不拦，范围条件显式拼 d.assignee_org_id） */
    @Select("<script>"
            + "SELECT e.user_id AS userId, SUM(e.hours) AS hours FROM effort_log e JOIN demand d ON e.demand_id = d.id "
            + "WHERE d.is_deleted = 0 "
            + "<if test='orgIds != null and !orgIds.isEmpty()'>"
            + "AND d.assignee_org_id IN <foreach collection='orgIds' item='o' open='(' separator=',' close=')'>#{o}</foreach>"
            + "</if>"
            + "GROUP BY e.user_id"
            + "</script>")
    List<Map<String, Object>> sumEffortByUser(@Param("orgIds") List<Long> orgIds);
}

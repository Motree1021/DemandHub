package com.demandhub.demand.dto;

import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

/**
 * 管理者看板 VO（FR-M6-01）：KPI 卡片 + 近12周趋势 + 类型分布 + 组织积压 Top N + SLA 健康度。
 * 数据范围与列表页一致（DataScopeInterceptor 自动按登录人过滤）：EXECUTIVE 全线，DEMAND_MANAGER 授权子树。
 */
@Data
public class ManagerBoardVO implements Serializable {

    private Kpi kpi;

    /** 近 12 周趋势（周桶升序） */
    private List<TrendPoint> trend;

    /** 类型分布（筛选范围内按提交量） */
    private List<TypeCount> typeDistribution;

    /** 组织积压 Top N（当前在途） */
    private List<OrgBacklog> orgBacklog;

    private SlaHealth slaHealth;

    @Data
    public static class Kpi implements Serializable {
        /** 本月新增（自然月，与列表页"本月"筛选对账） */
        private Long monthNew;
        /** 当前在途（非终态） */
        private Long inflight;
        /** 已完成（筛选范围内按关闭时间） */
        private Long done;
        /** 当前超 SLA（红色）数 */
        private Long slaOver;
        /** 平均交付周期（小时，筛选范围内 DONE 的 submitted→closed 均值） */
        private BigDecimal avgCycleHours;
    }

    @Data
    public static class TrendPoint implements Serializable {
        /** 周起始日期 yyyy-MM-dd（周一） */
        private String weekStart;
        private Long newCnt;
        private Long doneCnt;
    }

    @Data
    public static class TypeCount implements Serializable {
        private String typeCode;
        private String typeName;
        private Long cnt;
    }

    @Data
    public static class OrgBacklog implements Serializable {
        private Long orgId;
        private String orgName;
        private Long cnt;
    }

    @Data
    public static class SlaHealth implements Serializable {
        /** 正常（未达预警阈值或未配置 SLA） */
        private Long normal;
        /** 黄色预警（超过预警阈值） */
        private Long warn;
        /** 红色告警（已超最长停留） */
        private Long over;
    }
}

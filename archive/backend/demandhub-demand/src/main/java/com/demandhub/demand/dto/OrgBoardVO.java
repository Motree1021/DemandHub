package com.demandhub.demand.dto;

import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

/**
 * 经理看板 VO（FR-M6-02）：本承接组织维度。
 * 数据范围 = 当前经理授权组织子树（DataScopeInterceptor 自动过滤）。
 */
@Data
public class OrgBoardVO implements Serializable {

    /** 待受理数（SUBMITTED） */
    private Long pendingAccept;

    /** 需求池数（TRIAGE 待分派/待领取） */
    private Long pool;

    /** 处理中数（ANALYZING ~ ACCEPTANCE 在途） */
    private Long processing;

    /** 本周完成数（DONE 且本周关闭） */
    private Long weekDone;

    /** 人均在途数（在途 / 有在途的处理人数） */
    private BigDecimal avgInflightPerHandler;

    /** 团队成员工作量分布（人 × 在途需求数 × 累计工时） */
    private List<MemberWorkload> memberWorkload;

    @Data
    public static class MemberWorkload implements Serializable {
        private Long userId;
        private String userName;
        private Long inflightCnt;
        private BigDecimal effortHours;
    }
}

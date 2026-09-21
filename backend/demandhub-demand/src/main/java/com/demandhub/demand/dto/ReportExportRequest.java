package com.demandhub.demand.dto;

import io.swagger.v3.oas.annotations.media.Schema;

import java.time.LocalDate;

/**
 * 报表导出请求（FR-M6-04）：筛选口径与需求列表页一致。
 */
public record ReportExportRequest(
        @Schema(description = "报表类型：DEMAND_LIST 需求清单（默认）/ MONTHLY_REVIEW 月度复盘（预留）")
        String reportType,
        @Schema(description = "状态筛选") String status,
        @Schema(description = "需求类型") String demandTypeCode,
        @Schema(description = "紧急程度") String urgency,
        @Schema(description = "关键字（标题/编号模糊）") String keyword,
        @Schema(description = "仅看我提的/代提的") Boolean mine,
        @Schema(description = "提交时间起") LocalDate submittedFrom,
        @Schema(description = "提交时间止（含当日）") LocalDate submittedTo) {
}

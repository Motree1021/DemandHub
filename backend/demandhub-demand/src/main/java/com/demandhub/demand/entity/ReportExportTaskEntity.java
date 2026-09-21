package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 报表导出异步任务（report_export_task，FR-M6-04 / 架构 4.6）
 */
@Data
@TableName("report_export_task")
public class ReportExportTaskEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 任务编号 RPT-YYYYMMDD-NNN */
    private String taskNo;

    /** DEMAND_LIST 需求清单 / MONTHLY_REVIEW 月度复盘（预留） */
    private String reportType;

    /** 导出筛选参数 JSON */
    private String paramsJson;

    private Long requesterId;

    /** PENDING / RUNNING / SUCCESS / FAILED */
    private String status;

    /** MinIO 对象路径 */
    private String filePath;

    private String fileName;

    private String errorMsg;

    private LocalDateTime createdAt;

    private LocalDateTime finishedAt;
}

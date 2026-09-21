package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 需求只读视图（demand 表，agent 模块跨服务同库只读）。
 * 注意：本模块无 DataScopeInterceptor，权限在 Service 层自行校验。
 */
@Data
@TableName("demand")
public class DemandView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String demandNo;

    private String title;

    private String demandTypeCode;

    private String subtypeCode;

    private String content;

    private String urgency;

    private String status;

    private Integer onHold;

    private Long submitterId;

    private Long actualDemanderId;

    private Long submitterOrgId;

    private Long assigneeOrgId;

    private Long assigneeUserId;

    private LocalDateTime submittedAt;

    private LocalDateTime closedAt;

    private Integer isDeleted;
}

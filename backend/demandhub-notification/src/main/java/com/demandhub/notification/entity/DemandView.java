package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 需求只读视图（demand，同库只读；事件消费侧补充查询用）
 */
@Data
@TableName("demand")
public class DemandView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String demandNo;

    private String title;

    private String demandTypeCode;

    private String status;

    private Long submitterId;

    private Long actualDemanderId;

    private Long submitterOrgId;

    private Long assigneeOrgId;

    private Long assigneeUserId;

    @TableLogic
    private Integer isDeleted;
}

package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 用户镜像只读视图（demand_user_snapshot，同库只读）
 */
@Data
@TableName("demand_user_snapshot")
public class UserSnapshotView implements Serializable {

    @TableId(type = IdType.INPUT)
    private Long id;

    /** 权限中心用户唯一 ID，如 u_reporter_1 */
    private String userId;

    private String name;

    /** 企微 userid（企微推送接收人） */
    private String wecomId;

    private Long primaryOrgId;

    private String status;
}

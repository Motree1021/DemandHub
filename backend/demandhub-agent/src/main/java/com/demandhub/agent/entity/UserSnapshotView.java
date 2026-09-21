package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户镜像只读视图（demand_user_snapshot）
 */
@Data
@TableName("demand_user_snapshot")
public class UserSnapshotView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String userId;

    private String name;

    private Long primaryOrgId;

    private String status;
}

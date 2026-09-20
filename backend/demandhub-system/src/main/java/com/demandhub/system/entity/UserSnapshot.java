package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户只读镜像（demand_user_snapshot，来自零售统一权限中心，本地无 CRUD 界面）
 */
@Data
@TableName("demand_user_snapshot")
public class UserSnapshot implements Serializable {

    /** 数值 ID：与权限中心用户主键一致（同步时显式写入，保证业务表可稳定引用） */
    @TableId(type = IdType.INPUT)
    private Long id;

    private String userId;

    private String name;

    private String wecomId;

    private String employeeNo;

    private Long primaryOrgId;

    private String deptPath;

    private String phone;

    private String email;

    private String status;

    private LocalDateTime syncedAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

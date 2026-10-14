package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * DemandHub 自有用户（demand_user，OneID）。
 * 渠道接入版：用户主数据自有，渠道身份经 channel_user_mapping 映射到 OneID。
 * 过渡说明：userId 字符串已废弃（统一 BIGINT OneID），为兼容 JWT claims / 会话等既有代码，
 * 以 String.valueOf(id) 形式派生暴露，不落表。
 */
@Data
@TableName("demand_user")
public class UserSnapshot implements Serializable {

    /** DemandHub OneID（自增；种子数据由 SQL 显式指定 id，兼容 INPUT 场景） */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 已废弃的字符串用户标识：派生为 String.valueOf(id)，仅供旧会话/JWT 代码过渡使用 */
    @TableField(exist = false)
    private String userId;

    private String name;

    /** PC 登录账号（唯一） */
    private String loginName;

    /** BCrypt 密码哈希（仅 PC 账号密码登录；出参严禁回显） */
    private String passwordHash;

    /** 密码最近修改时间；NULL 表示需强制改密 */
    private java.time.LocalDateTime passwordUpdatedAt;

    /** 创金零售 verify 回传的企微 userid（自动匹配键） */
    @TableField("wecom_userid")
    private String wecomId;

    private String employeeNo;

    private Long primaryOrgId;

    /** 部门名称路径（如 创金合信零售业务线/财管科技产品部）：由组织树派生，不落表 */
    @TableField(exist = false)
    private String deptPath;

    private String phone;

    private String email;

    private Integer isEmployee;

    /** PENDING/ACTIVE/DISABLED/MERGED */
    private String status;

    private Long mergedToUserId;

    private String lastLoginChannel;

    private LocalDateTime lastLoginAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    public String getUserId() {
        return id == null ? null : String.valueOf(id);
    }

    /** 兼容旧代码调用，值不再落表（userId 由 id 派生） */
    public void setUserId(String userId) {
        // no-op
    }
}

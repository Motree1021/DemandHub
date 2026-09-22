package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * DemandHub 组织树（demand_org，管理员可 CRUD）。
 * orgId 与主键 id 同义（组织 id 即 100/110/111...），为兼容旧代码派生暴露。
 */
@Data
@TableName("demand_org")
public class OrgSnapshot implements Serializable {

    /** 组织 ID（即原权限中心 org_id，100~141 保留；管理端新增时自增回填用于 path 物化） */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 与 id 同义，兼容旧代码 */
    @TableField(exist = false)
    private Long orgId;

    private String name;

    /** LINE/DEPT/GROUP */
    private String level;

    private Long parentId;

    /** 物化路径，如 /100/110/（尾斜杠），数据权限按前缀匹配子树 */
    private String path;

    /** REPORTER/ASSIGNER/BOTH */
    private String orgKind;

    /** 是否外部虚拟组织 */
    private Integer externalFlag;

    /** 渠道侧部门ID（创金零售/企微部门ID），票据登录部门映射用 */
    private String externalDeptId;

    private String status;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    public Long getOrgId() {
        return id;
    }

    /** 兼容旧代码调用，值不再单独落表（orgId 与 id 同义） */
    public void setOrgId(Long orgId) {
        // no-op
    }
}

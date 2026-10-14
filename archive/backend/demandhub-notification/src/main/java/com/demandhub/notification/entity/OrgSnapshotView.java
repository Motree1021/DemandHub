package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 组织只读视图（demand_org，同库只读；子树前缀匹配用）
 */
@Data
@TableName("demand_org")
public class OrgSnapshotView implements Serializable {

    /** 组织 ID（100~141 保留） */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 与 id 同义，兼容旧代码 */
    @TableField(exist = false)
    private Long orgId;

    private String name;

    private Long parentId;

    /** 物化路径，如 /100/110/（尾斜杠），子树按前缀匹配 */
    private String path;

    private String status;

    public Long getOrgId() {
        return id;
    }

    /** 兼容旧代码调用，值不再单独落表 */
    public void setOrgId(Long orgId) {
        // no-op
    }
}

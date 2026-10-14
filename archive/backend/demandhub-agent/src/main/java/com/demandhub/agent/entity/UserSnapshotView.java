package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 用户只读视图（demand_user，同库只读）
 */
@Data
@TableName("demand_user")
public class UserSnapshotView implements Serializable {

    /** DemandHub OneID */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 已废弃的字符串用户标识：派生为 String.valueOf(id)，不落表 */
    @TableField(exist = false)
    private String userId;

    private String name;

    private Long primaryOrgId;

    private String status;

    public String getUserId() {
        return id == null ? null : String.valueOf(id);
    }

    /** 兼容旧代码调用，值不再落表 */
    public void setUserId(String userId) {
        // no-op
    }
}

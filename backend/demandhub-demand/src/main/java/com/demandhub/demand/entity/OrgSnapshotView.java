package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 组织镜像只读视图（demand_org_snapshot，同库只读）
 */
@Data
@TableName("demand_org_snapshot")
public class OrgSnapshotView implements Serializable {

    @TableId(type = IdType.INPUT)
    private Long id;

    private Long orgId;

    private String name;

    private Long parentId;

    /** 物化路径，如 /100/110/111，子树按前缀匹配 */
    private String path;

    private String status;
}

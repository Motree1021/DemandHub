package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 组织节点只读镜像（demand_org_snapshot，来自零售统一权限中心）
 */
@Data
@TableName("demand_org_snapshot")
public class OrgSnapshot implements Serializable {

    /** 数值 ID：与权限中心组织主键一致 */
    @TableId(type = IdType.INPUT)
    private Long id;

    private Long orgId;

    private String name;

    /** LINE/DEPT/GROUP */
    private String level;

    private Long parentId;

    /** 物化路径，如 /100/110/111，数据权限按前缀匹配子树 */
    private String path;

    /** REPORTER/ASSIGNER/BOTH */
    private String orgKind;

    private String status;

    private LocalDateTime syncedAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

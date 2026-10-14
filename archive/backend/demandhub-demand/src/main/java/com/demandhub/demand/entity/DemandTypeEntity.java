package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 需求类型字典（demand_type）
 */
@Data
@TableName("demand_type")
public class DemandTypeEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** TECH / MATL / TRAIN */
    private String typeCode;

    private String typeName;

    private String parentTypeCode;

    /** 默认承接组织 */
    private Long defaultOrgId;

    private String stateMachineKey;

    private String slaConfig;

    private Integer sort;

    private String status;
}

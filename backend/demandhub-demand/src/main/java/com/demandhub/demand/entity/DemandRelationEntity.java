package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 需求关联（demand_relation，uk: demand_id + related_demand_id + relation_type）
 */
@Data
@TableName("demand_relation")
public class DemandRelationEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 主需求 */
    private Long demandId;

    /** 关联需求 */
    private Long relatedDemandId;

    /** PARENT / DEPENDS / DUPLICATE / SPLIT */
    private String relationType;
}

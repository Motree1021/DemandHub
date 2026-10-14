package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 科技需求扩展（demand_ext_tech，1:1）
 */
@Data
@TableName("demand_ext_tech")
public class DemandExtTechEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    /** 需求子类（TECH_SUBTYPE 字典：SYS_DEV/DATA_RPT/SYS_INT/OPS_OPT/OTHER） */
    private String techSubtype;

    private String relatedSystem;

    private String relatedModule;

    private String businessScenario;

    private String acceptanceCriteria;
}

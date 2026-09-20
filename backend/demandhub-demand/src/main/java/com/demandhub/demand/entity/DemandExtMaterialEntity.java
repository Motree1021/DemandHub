package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 物料需求扩展（demand_ext_material，1:1）
 */
@Data
@TableName("demand_ext_material")
public class DemandExtMaterialEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private String materialSubtype;

    private String usageScenario;

    private Integer quantity;

    private LocalDateTime expectedArrivalAt;
}

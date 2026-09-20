package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 培训需求扩展（demand_ext_training，1:1）
 */
@Data
@TableName("demand_ext_training")
public class DemandExtTrainingEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private String trainingSubtype;

    private String traineeObject;

    private Integer traineeCount;

    private LocalDateTime expectedCompleteAt;
}

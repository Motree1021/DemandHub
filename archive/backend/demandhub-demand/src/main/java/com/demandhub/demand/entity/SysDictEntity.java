package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;

/**
 * 通用字典（sys_dict，按 dict_type 分组：紧急程度/关闭原因/挂起原因等）
 */
@Data
@TableName("sys_dict")
public class SysDictEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String dictType;

    private String itemCode;

    private String itemName;

    private Integer sort;

    private String status;
}

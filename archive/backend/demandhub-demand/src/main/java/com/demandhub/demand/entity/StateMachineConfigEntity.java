package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 状态机配置（state_machine_config，M8：JSON 存储，热加载不重启）
 */
@Data
@TableName("state_machine_config")
public class StateMachineConfigEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 配置标识，demand_type.state_machine_key 引用 */
    private String configKey;

    private String configName;

    /** 流转规则 JSON：{"rules":[{"from","event","to","roles","remark"}]} */
    private String configJson;

    private String status;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

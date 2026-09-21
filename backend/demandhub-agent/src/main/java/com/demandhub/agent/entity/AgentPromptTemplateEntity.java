package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Prompt 模板（agent_prompt_template，一期存库可配置，二期可迁 Nacos）
 */
@Data
@TableName("agent_prompt_template")
public class AgentPromptTemplateEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** SUBMIT_GUIDE / HANDLE_ASSIST_QUESTIONS / HANDLE_ASSIST_SOLUTION */
    private String templateCode;

    private String templateName;

    /** Prompt 模板，支持 ${var} 占位 */
    private String content;

    private String status;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

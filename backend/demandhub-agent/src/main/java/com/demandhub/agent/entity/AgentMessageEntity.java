package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent 会话消息（agent_message）
 */
@Data
@TableName("agent_message")
public class AgentMessageEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long sessionId;

    /** USER / ASSISTANT / SYSTEM */
    private String role;

    private String content;

    /** 结构化产出 JSON（如表单字段回填 payload） */
    private String structuredPayload;

    private LocalDateTime createdAt;
}

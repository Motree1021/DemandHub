package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent 会话（agent_session，FR-M9-01/02）
 */
@Data
@TableName("agent_session")
public class AgentSessionEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 会话编号（UUID） */
    private String sessionNo;

    private Long userId;

    /** SUBMIT_GUIDE 提报启发 / HANDLE_ASSIST 处理辅助 */
    private String scene;

    /** 处理辅助场景关联需求 */
    private Long demandId;

    private String title;

    /** ACTIVE / CLOSED */
    private String status;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent 产出草稿区（agent_draft，FR-M9-02：AI 生成需人工确认，确认后才入正式表）
 */
@Data
@TableName("agent_draft")
public class AgentDraftEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Long sessionId;

    /** QUESTIONS 调研问题清单 / SOLUTION 方案初稿 */
    private String draftType;

    /** 内容（SOLUTION 类型为 JSON：{specContent, solutionContent}） */
    private String content;

    /** PENDING 待确认 / CONFIRMED 已入库 / DISCARDED 已废弃 */
    private String status;

    private Long confirmedBy;

    private LocalDateTime confirmedAt;

    /** 确认后写入的 solution.id */
    private Long targetSolutionId;

    private Long createdBy;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

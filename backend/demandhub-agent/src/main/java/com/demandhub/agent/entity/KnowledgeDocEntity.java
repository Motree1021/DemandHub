package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * RAG 知识库（knowledge_doc，FR-M9-03）。
 * 向量存 JSON 列（一期 Mock embedding，应用层余弦相似度）；
 * 二期替换 pgvector 时仅需改 embedding 列类型与检索 SQL，表结构与接口保持不变。
 */
@Data
@TableName("knowledge_doc")
public class KnowledgeDocEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 来源需求（DONE） */
    private Long demandId;

    private String demandNo;

    private String title;

    private String demandTypeCode;

    /** 向量化文本（方案 + 评审意见 + SOP 摘要） */
    private String content;

    /** 向量 JSON 数组 */
    private String embedding;

    private String status;

    private LocalDateTime createdAt;
}

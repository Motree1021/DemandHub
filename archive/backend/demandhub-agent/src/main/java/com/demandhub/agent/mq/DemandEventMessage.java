package com.demandhub.agent.mq;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

/**
 * 需求领域事件报文（demand 模块 DemandEventRelay 发送，agent 模块只取 RAG 关心的字段）
 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class DemandEventMessage {

    private Long demandId;

    private String demandNo;

    /** 事件名：SUBMIT/ACCEPT/ASSIGN/.../ACCEPT_PASS 等 */
    private String event;

    private String toStatus;

    private String title;
}

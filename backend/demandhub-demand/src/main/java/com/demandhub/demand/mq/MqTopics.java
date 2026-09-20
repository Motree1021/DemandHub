package com.demandhub.demand.mq;

/**
 * MQ 主题常量。
 */
public final class MqTopics {

    /** 需求领域事件（流转 / SLA 告警），生产者：demand 服务；消费者：notification 服务 */
    public static final String DEMAND_EVENT_TOPIC = "demandhub-demand-event";

    private MqTopics() {
    }
}

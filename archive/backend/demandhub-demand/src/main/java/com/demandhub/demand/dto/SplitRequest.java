package com.demandhub.demand.dto;

import java.util.List;

/**
 * 拆分子需求请求（子需求独立编号，直接入父需求承接组织需求池）
 */
public record SplitRequest(String title,
                           String content,
                           String urgency,
                           Long actualDemanderId,
                           List<Long> attachmentIds) {
}

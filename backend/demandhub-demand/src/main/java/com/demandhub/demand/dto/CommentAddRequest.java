package com.demandhub.demand.dto;

import java.util.List;

/**
 * 评论新增请求（mentionedUserIds 为 @人列表）
 */
public record CommentAddRequest(Long demandId,
                                String content,
                                List<Long> mentionedUserIds,
                                List<Long> attachmentIds) {
}

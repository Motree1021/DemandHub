package com.demandhub.demand.dto;

import java.util.List;

/**
 * 评论补充请求（仅作者可追加补充，评论不可删除）
 */
public record CommentUpdateRequest(String content, List<Long> mentionedUserIds) {
}

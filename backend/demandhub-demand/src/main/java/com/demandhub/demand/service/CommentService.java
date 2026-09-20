package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.CommentAddRequest;
import com.demandhub.demand.dto.CommentUpdateRequest;
import com.demandhub.demand.entity.CommentEntity;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.mapper.CommentMapper;
import com.demandhub.demand.mapper.DemandMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

/**
 * M4 评论沟通（FR-M4-07）：文字 + 附件 + @人；评论不可删除，仅作者可追加补充。
 */
@Service
public class CommentService {

    private final CommentMapper commentMapper;
    private final DemandMapper demandMapper;
    private final AttachmentService attachmentService;

    public CommentService(CommentMapper commentMapper, DemandMapper demandMapper,
                          AttachmentService attachmentService) {
        this.commentMapper = commentMapper;
        this.demandMapper = demandMapper;
        this.attachmentService = attachmentService;
    }

    @Transactional(rollbackFor = Exception.class)
    public CommentEntity add(CommentAddRequest request) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(request.content())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "评论内容不能为空");
        }
        requireVisible(request.demandId());
        CommentEntity comment = new CommentEntity();
        comment.setDemandId(request.demandId());
        comment.setAuthorId(user.getId());
        comment.setContent(request.content().trim());
        if (request.mentionedUserIds() != null && !request.mentionedUserIds().isEmpty()) {
            comment.setMentionedUserIds(request.mentionedUserIds().stream()
                    .map(String::valueOf).collect(Collectors.joining(",")));
        }
        commentMapper.insert(comment);
        attachmentService.rebind(request.attachmentIds(), "COMMENT", comment.getId());
        return comment;
    }

    /** 追加补充（仅作者本人；评论不可删除） */
    @Transactional(rollbackFor = Exception.class)
    public CommentEntity update(Long commentId, CommentUpdateRequest request) {
        CurrentUser user = requireLogin();
        CommentEntity comment = commentMapper.selectById(commentId);
        if (comment == null) {
            throw new BizException(ErrorCode.COMMENT_NOT_FOUND);
        }
        if (!user.getId().equals(comment.getAuthorId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅评论作者可补充");
        }
        if (!StringUtils.hasText(request.content())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "评论内容不能为空");
        }
        comment.setContent(request.content().trim());
        if (request.mentionedUserIds() != null) {
            comment.setMentionedUserIds(request.mentionedUserIds().stream()
                    .map(String::valueOf).collect(Collectors.joining(",")));
        }
        commentMapper.updateById(comment);
        return comment;
    }

    public List<CommentEntity> listByDemand(Long demandId) {
        requireVisible(demandId);
        return commentMapper.selectList(new LambdaQueryWrapper<CommentEntity>()
                .eq(CommentEntity::getDemandId, demandId)
                .orderByAsc(CommentEntity::getId));
    }

    private DemandEntity requireVisible(Long demandId) {
        DemandEntity demand = demandMapper.selectById(demandId);
        if (demand == null) {
            throw new BizException(ErrorCode.DEMAND_NOT_FOUND, "需求不存在或无权限访问");
        }
        return demand;
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}

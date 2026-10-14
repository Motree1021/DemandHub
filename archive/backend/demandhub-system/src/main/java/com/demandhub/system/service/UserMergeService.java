package com.demandhub.system.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.UserMergeMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

/**
 * 用户合并（FR-M1-01，开发计划任务 2.3）。
 * 将源用户的业务数据（需求/评论/工时/分派/渠道映射及同源用户所有数据）迁移到目标用户，
 * 源用户置 MERGED 并指向目标 OneID；此后源用户的渠道身份登录经 ChannelUserMatcher 自动跳转目标用户。
 * 源用户授权不自动继承（逻辑删除），避免静默扩权；管理端合并对话框先调 {@link #preview} 做影响预览。
 */
@Slf4j
@Service
public class UserMergeService {

    private final UserMergeMapper mergeMapper;
    private final UserService userService;
    private final SessionService sessionService;

    public UserMergeService(UserMergeMapper mergeMapper, UserService userService, SessionService sessionService) {
        this.mergeMapper = mergeMapper;
        this.userService = userService;
        this.sessionService = sessionService;
    }

    /** 合并影响预览（各清单待迁移行数） */
    public Map<String, Long> preview(Long sourceUserId) {
        return mergeMapper.preview(sourceUserId);
    }

    /**
     * 执行合并（事务）。管理端接口在 P4 提供（用户管理-合并对话框，ADMIN）。
     *
     * @param sourceUserId 被合并（废弃）的用户
     * @param targetUserId 保留的目标用户（须 ACTIVE）
     * @param operatorId   操作人（审计）
     */
    @Transactional
    public void merge(Long sourceUserId, Long targetUserId, Long operatorId) {
        if (sourceUserId == null || targetUserId == null || sourceUserId.equals(targetUserId)) {
            throw new BizException(ErrorCode.MERGE_TARGET_INVALID, "源用户与目标用户不能相同");
        }
        UserSnapshot source = userService.findById(sourceUserId);
        UserSnapshot target = userService.findById(targetUserId);
        if (source == null || target == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        if ("MERGED".equals(source.getStatus())) {
            throw new BizException(ErrorCode.MERGE_TARGET_INVALID, "源用户已被合并");
        }
        if (!"ACTIVE".equals(target.getStatus())) {
            throw new BizException(ErrorCode.MERGE_TARGET_INVALID, "目标用户须为 ACTIVE 状态");
        }

        // 需求
        int n = mergeMapper.migrateDemandSubmitter(sourceUserId, targetUserId)
                + mergeMapper.migrateDemandActualDemander(sourceUserId, targetUserId)
                + mergeMapper.migrateDemandAssignee(sourceUserId, targetUserId)
                + mergeMapper.migrateDemandCreatedBy(sourceUserId, targetUserId)
                + mergeMapper.migrateDemandUpdatedBy(sourceUserId, targetUserId);
        // 评论/工时/分派/映射
        n += mergeMapper.migrateCommentAuthor(sourceUserId, targetUserId)
                + mergeMapper.migrateEffortUser(sourceUserId, targetUserId)
                + mergeMapper.migrateAssignmentAssignee(sourceUserId, targetUserId)
                + mergeMapper.migrateAssignmentDispatcher(sourceUserId, targetUserId)
                + mergeMapper.migrateChannelMapping(sourceUserId, targetUserId);
        // 同源用户所有数据
        n += mergeMapper.migrateSolutionAuthor(sourceUserId, targetUserId)
                + mergeMapper.migrateReviewReviewer(sourceUserId, targetUserId)
                + mergeMapper.migrateTransitionOperator(sourceUserId, targetUserId)
                + mergeMapper.migrateDraftUser(sourceUserId, targetUserId)
                + mergeMapper.migrateAttachmentUploader(sourceUserId, targetUserId);

        int grants = mergeMapper.retireSourceGrants(sourceUserId);
        userService.markMerged(sourceUserId, targetUserId);
        // 源用户全清会话（含 refresh），立即失效
        sessionService.deleteAllSessionsByUser(String.valueOf(sourceUserId));
        log.info("用户合并完成: source={} → target={}, 迁移行数={}, 回收授权={}, operator={}",
                sourceUserId, targetUserId, n, grants, operatorId);
    }
}

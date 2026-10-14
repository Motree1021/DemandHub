package com.demandhub.system.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.UserMergeMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * 用户合并单测（P7 任务 7.1，FR-M1-01 任务 2.3）。
 * 校验拦截（自合并/源已 MERGED/目标非 ACTIVE）；全量迁移编排 + 授权回收 +
 * 源用户置 MERGED + 会话双清（密码变更/合并粒度）。
 */
@ExtendWith(MockitoExtension.class)
class UserMergeServiceTest {

    @Mock
    private UserMergeMapper mergeMapper;
    @Mock
    private UserService userService;
    @Mock
    private SessionService sessionService;
    @InjectMocks
    private UserMergeService mergeService;

    private static UserSnapshot user(Long id, String status) {
        UserSnapshot u = new UserSnapshot();
        u.setId(id);
        u.setStatus(status);
        return u;
    }

    private static BizException assertBiz(Runnable r, ErrorCode code) {
        BizException ex = assertThrows(BizException.class, r::run);
        assertEquals(code.getCode(), ex.getCode());
        return ex;
    }

    @Test
    void merge_sameSourceAndTarget_rejected() {
        assertBiz(() -> mergeService.merge(1L, 1L, 1001L), ErrorCode.MERGE_TARGET_INVALID);
        verifyNoInteractions(mergeMapper);
    }

    @Test
    void merge_sourceNotFound_rejected() {
        when(userService.findById(1L)).thenReturn(null);
        when(userService.findById(2L)).thenReturn(user(2L, "ACTIVE"));

        assertBiz(() -> mergeService.merge(1L, 2L, 1001L), ErrorCode.USER_NOT_FOUND);
        verifyNoInteractions(mergeMapper);
    }

    @Test
    void merge_sourceAlreadyMerged_rejected() {
        UserSnapshot source = user(1L, "MERGED");
        source.setMergedToUserId(9L);
        when(userService.findById(1L)).thenReturn(source);
        when(userService.findById(2L)).thenReturn(user(2L, "ACTIVE"));

        assertBiz(() -> mergeService.merge(1L, 2L, 1001L), ErrorCode.MERGE_TARGET_INVALID);
        verifyNoInteractions(mergeMapper);
    }

    @Test
    void merge_targetNotActive_rejected() {
        when(userService.findById(1L)).thenReturn(user(1L, "ACTIVE"));
        when(userService.findById(2L)).thenReturn(user(2L, "DISABLED"));

        assertBiz(() -> mergeService.merge(1L, 2L, 1001L), ErrorCode.MERGE_TARGET_INVALID);
        verifyNoInteractions(mergeMapper);
    }

    @Test
    void merge_happyPath_migratesAllRetiresGrantsMarksMergedAndClearsSessions() {
        when(userService.findById(1L)).thenReturn(user(1L, "ACTIVE"));
        when(userService.findById(2L)).thenReturn(user(2L, "ACTIVE"));
        when(mergeMapper.retireSourceGrants(1L)).thenReturn(3);

        mergeService.merge(1L, 2L, 1001L);

        // 需求 5 路 + 评论/工时/分派/映射 + 同源数据 5 路，全部迁移到目标用户
        verify(mergeMapper).migrateDemandSubmitter(1L, 2L);
        verify(mergeMapper).migrateDemandActualDemander(1L, 2L);
        verify(mergeMapper).migrateDemandAssignee(1L, 2L);
        verify(mergeMapper).migrateDemandCreatedBy(1L, 2L);
        verify(mergeMapper).migrateDemandUpdatedBy(1L, 2L);
        verify(mergeMapper).migrateCommentAuthor(1L, 2L);
        verify(mergeMapper).migrateEffortUser(1L, 2L);
        verify(mergeMapper).migrateAssignmentAssignee(1L, 2L);
        verify(mergeMapper).migrateAssignmentDispatcher(1L, 2L);
        verify(mergeMapper).migrateChannelMapping(1L, 2L);
        verify(mergeMapper).migrateSolutionAuthor(1L, 2L);
        verify(mergeMapper).migrateReviewReviewer(1L, 2L);
        verify(mergeMapper).migrateTransitionOperator(1L, 2L);
        verify(mergeMapper).migrateDraftUser(1L, 2L);
        verify(mergeMapper).migrateAttachmentUploader(1L, 2L);
        // 源用户授权不自动继承（逻辑删除），避免静默扩权
        verify(mergeMapper).retireSourceGrants(1L);
        // 源用户置 MERGED 指向目标 OneID
        verify(userService).markMerged(1L, 2L);
        // 源用户会话全清（含 refresh），立即失效
        verify(sessionService).deleteAllSessionsByUser("1");
    }

    @Test
    void preview_delegatesToMapper() {
        Map<String, Long> expected = Map.of("demand", 3L, "comment", 5L);
        when(mergeMapper.preview(1L)).thenReturn(expected);

        Map<String, Long> actual = mergeService.preview(1L);

        assertSame(expected, actual);
    }
}

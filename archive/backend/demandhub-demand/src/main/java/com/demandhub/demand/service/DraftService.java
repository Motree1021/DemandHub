package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.DraftSaveRequest;
import com.demandhub.demand.entity.DemandDraftEntity;
import com.demandhub.demand.mapper.DemandDraftMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

/**
 * 草稿服务（FR-M2-03）：仅本人可见/可编辑；提交后转为正式需求（converted_demand_id 关联）。
 */
@Service
public class DraftService {

    private final DemandDraftMapper draftMapper;

    public DraftService(DemandDraftMapper draftMapper) {
        this.draftMapper = draftMapper;
    }

    public DemandDraftEntity save(DraftSaveRequest request) {
        CurrentUser current = UserContext.get();
        Long currentUserId = UserContext.currentUserId();
        DemandDraftEntity draft;
        if (request.id() == null) {
            draft = new DemandDraftEntity();
            draft.setUserId(currentUserId);
        } else {
            draft = draftMapper.selectById(request.id());
            if (draft == null || !currentUserId.equals(draft.getUserId())) {
                throw new BizException(ErrorCode.DRAFT_NOT_FOUND);
            }
            if (draft.getConvertedDemandId() != null) {
                throw new BizException(ErrorCode.BIZ_ERROR, "草稿已提交为正式需求，不可再编辑");
            }
        }
        // 来源渠道只信会话 claims（网关注入 X-Channel），不接收前端传值（P5 任务 5.5）
        draft.setChannel(current != null && StringUtils.hasText(current.getChannel())
                ? current.getChannel() : "WEB");
        draft.setFormPayload(request.formPayload());
        if (draft.getId() == null) {
            draftMapper.insert(draft);
        } else {
            draftMapper.updateById(draft);
        }
        return draft;
    }

    public List<DemandDraftEntity> listMine() {
        return draftMapper.selectList(new LambdaQueryWrapper<DemandDraftEntity>()
                .eq(DemandDraftEntity::getUserId, UserContext.currentUserId())
                .orderByDesc(DemandDraftEntity::getUpdatedAt));
    }

    public DemandDraftEntity getMine(Long id) {
        DemandDraftEntity draft = draftMapper.selectById(id);
        if (draft == null || !UserContext.currentUserId().equals(draft.getUserId())) {
            throw new BizException(ErrorCode.DRAFT_NOT_FOUND);
        }
        return draft;
    }

    public void deleteMine(Long id) {
        DemandDraftEntity draft = getMine(id);
        if (draft.getConvertedDemandId() != null) {
            throw new BizException(ErrorCode.BIZ_ERROR, "草稿已提交为正式需求，不可删除");
        }
        draftMapper.deleteById(id);
    }

    /** 提交时校验草稿归属并返回（可为空） */
    public DemandDraftEntity requireConvertible(Long draftId) {
        if (draftId == null) {
            return null;
        }
        DemandDraftEntity draft = getMine(draftId);
        if (draft.getConvertedDemandId() != null) {
            throw new BizException(ErrorCode.BIZ_ERROR, "草稿已提交过，请勿重复提交");
        }
        return draft;
    }

    public void markConverted(DemandDraftEntity draft, Long demandId) {
        if (draft == null) {
            return;
        }
        draft.setConvertedDemandId(demandId);
        draftMapper.updateById(draft);
    }
}

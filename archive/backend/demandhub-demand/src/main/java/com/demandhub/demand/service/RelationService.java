package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.SplitRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandRelationEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandRelationMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;

/**
 * M4 需求关联（FR-M4-08）与拆分（FR-M4-04）：
 * 父子/依赖/重复/拆分，双向可见；拆分子需求独立编号、直接入父需求承接组织需求池。
 */
@Service
public class RelationService {

    private static final Set<String> RELATION_TYPES = Set.of("PARENT", "DEPENDS", "DUPLICATE", "SPLIT");

    private final DemandRelationMapper relationMapper;
    private final DemandMapper demandMapper;
    private final DemandTransitionLogMapper transitionLogMapper;
    private final DemandNoGenerator demandNoGenerator;
    private final AttachmentService attachmentService;
    private final UserLookupService userLookupService;

    public RelationService(DemandRelationMapper relationMapper, DemandMapper demandMapper,
                           DemandTransitionLogMapper transitionLogMapper,
                           DemandNoGenerator demandNoGenerator, AttachmentService attachmentService,
                           UserLookupService userLookupService) {
        this.relationMapper = relationMapper;
        this.demandMapper = demandMapper;
        this.transitionLogMapper = transitionLogMapper;
        this.demandNoGenerator = demandNoGenerator;
        this.attachmentService = attachmentService;
        this.userLookupService = userLookupService;
    }

    @Transactional(rollbackFor = Exception.class)
    public DemandRelationEntity add(Long demandId, Long relatedDemandId, String relationType) {
        requireLogin();
        if (!RELATION_TYPES.contains(relationType)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "关联类型必须为 PARENT/DEPENDS/DUPLICATE/SPLIT");
        }
        if (demandId.equals(relatedDemandId)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "需求不能关联自身");
        }
        requireVisible(demandId);
        requireVisible(relatedDemandId);
        DemandRelationEntity relation = new DemandRelationEntity();
        relation.setDemandId(demandId);
        relation.setRelatedDemandId(relatedDemandId);
        relation.setRelationType(relationType);
        try {
            relationMapper.insert(relation);
        } catch (org.springframework.dao.DuplicateKeyException e) {
            throw new BizException(ErrorCode.BIZ_ERROR, "该关联已存在");
        }
        return relation;
    }

    public void remove(Long relationId) {
        requireLogin();
        DemandRelationEntity relation = relationMapper.selectById(relationId);
        if (relation == null) {
            throw new BizException(ErrorCode.RELATION_NOT_FOUND);
        }
        relationMapper.deleteById(relationId);
    }

    /** 双向可见：查出“我关联别人”和“别人关联我” */
    public List<DemandRelationEntity> listByDemand(Long demandId) {
        requireVisible(demandId);
        return relationMapper.selectList(new LambdaQueryWrapper<DemandRelationEntity>()
                .eq(DemandRelationEntity::getDemandId, demandId)
                .or()
                .eq(DemandRelationEntity::getRelatedDemandId, demandId)
                .orderByAsc(DemandRelationEntity::getId));
    }

    /**
     * 拆分子需求：独立编号、直接入父需求承接组织需求池（TRIAGE），关联类型 SPLIT。
     */
    @Transactional(rollbackFor = Exception.class)
    public DemandEntity split(Long parentId, SplitRequest request) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(request.title())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "子需求标题不能为空");
        }
        DemandEntity parent = requireVisible(parentId);
        if (!StringUtils.hasText(request.content())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "子需求内容不能为空");
        }
        LocalDateTime now = LocalDateTime.now();
        DemandEntity child = new DemandEntity();
        child.setDemandNo(demandNoGenerator.next(parent.getDemandTypeCode()));
        child.setTitle(request.title().trim());
        child.setDemandTypeCode(parent.getDemandTypeCode());
        child.setSubtypeCode(parent.getSubtypeCode());
        child.setContent(request.content());
        child.setUrgency(StringUtils.hasText(request.urgency()) ? request.urgency() : parent.getUrgency());
        child.setStatus("TRIAGE");
        child.setOnHold(0);
        child.setSubmitterId(user.getId());
        child.setActualDemanderId(request.actualDemanderId());
        UserSnapshotView submitter = userLookupService.getById(user.getId());
        if (submitter != null) {
            child.setSubmitterOrgId(submitter.getPrimaryOrgId());
            child.setSubmitterOrgSnapshot(submitter.getDeptPath());
        }
        child.setChannel("WEB");
        child.setAssigneeOrgId(parent.getAssigneeOrgId());
        child.setSubmittedAt(now);
        demandMapper.insert(child);

        // 关联：父 --SPLIT--> 子
        DemandRelationEntity relation = new DemandRelationEntity();
        relation.setDemandId(parentId);
        relation.setRelatedDemandId(child.getId());
        relation.setRelationType("SPLIT");
        relationMapper.insert(relation);

        // 子需求创建留痕（非状态机流转：新建即入池，from 为空）
        DemandTransitionLogEntity log = new DemandTransitionLogEntity();
        log.setDemandId(child.getId());
        log.setFromStatus(null);
        log.setToStatus("TRIAGE");
        log.setAction("SPLIT");
        log.setOperatorId(user.getId());
        log.setOperatorSnapshot(userLookupService.nameOf(user.getId()));
        log.setComment("由需求 " + parent.getDemandNo() + " 拆分创建");
        transitionLogMapper.insert(log);

        attachmentService.rebind(request.attachmentIds(), "DEMAND", child.getId());
        return child;
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

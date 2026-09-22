package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.ResubmitRequest;
import com.demandhub.demand.dto.SubmitRequest;
import com.demandhub.demand.entity.DemandDraftEntity;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;

/**
 * M2 需求提报：提交（编号生成 + 类型路由 + 扩展表 + 附件绑定 + 代办）、撤销、补充重提。
 */
@Service
public class DemandSubmitService {

    private final DemandMapper demandMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final DemandNoGenerator demandNoGenerator;
    private final DemandStateMachine stateMachine;
    private final DemandExtService extService;
    private final DraftService draftService;
    private final AttachmentService attachmentService;
    private final UserLookupService userLookupService;

    public DemandSubmitService(DemandMapper demandMapper, DemandTypeMapper demandTypeMapper,
                               DemandNoGenerator demandNoGenerator, DemandStateMachine stateMachine,
                               DemandExtService extService, DraftService draftService,
                               AttachmentService attachmentService, UserLookupService userLookupService) {
        this.demandMapper = demandMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.demandNoGenerator = demandNoGenerator;
        this.stateMachine = stateMachine;
        this.extService = extService;
        this.draftService = draftService;
        this.attachmentService = attachmentService;
        this.userLookupService = userLookupService;
    }

    /**
     * 提交需求（FR-M2-06）：生成编号、按类型路由默认承接组织、DRAFT → SUBMITTED。
     * 支持草稿转化与代办提报（actual_demander_id）。
     */
    @Transactional(rollbackFor = Exception.class)
    public DemandEntity submit(SubmitRequest request) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(request.title())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "标题不能为空");
        }
        if (!StringUtils.hasText(request.content())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "需求内容不能为空");
        }
        DemandTypeEntity type = requireActiveType(request.demandTypeCode());
        DemandDraftEntity draft = draftService.requireConvertible(request.draftId());
        if (request.actualDemanderId() != null && !userLookupService.exists(request.actualDemanderId())) {
            throw new BizException(ErrorCode.USER_NOT_FOUND, "实际需求人不存在");
        }

        LocalDateTime now = LocalDateTime.now();
        DemandEntity demand = new DemandEntity();
        demand.setDemandNo(demandNoGenerator.next(type.getTypeCode()));
        demand.setTitle(request.title().trim());
        demand.setDemandTypeCode(type.getTypeCode());
        demand.setSubtypeCode(request.subtypeCode());
        demand.setContent(request.content());
        demand.setUrgency(StringUtils.hasText(request.urgency()) ? request.urgency() : "NORMAL");
        demand.setStatus("DRAFT");
        demand.setOnHold(0);
        demand.setSubmitterId(user.getId());
        demand.setActualDemanderId(request.actualDemanderId());
        UserSnapshotView submitter = userLookupService.getById(user.getId());
        if (submitter != null) {
            demand.setSubmitterOrgId(submitter.getPrimaryOrgId());
            demand.setSubmitterOrgSnapshot(submitter.getDeptPath());
        }
        // 来源渠道只信会话 claims（网关注入 X-Channel），不接收前端传值，伪造无效（P5 任务 5.5）
        demand.setChannel(StringUtils.hasText(user.getChannel()) ? user.getChannel() : "WEB");
        // 路由策略（架构 4.2）：一期按类型默认承接组织；未配置则进需求管理者队列（assignee_org_id 为空）
        demand.setAssigneeOrgId(type.getDefaultOrgId());
        demand.setExpectDeliveryAt(request.expectDeliveryAt());
        demand.setSubmittedAt(now);
        demandMapper.insert(demand);

        // 三类扩展表写入
        extService.writeExt(demand.getId(), type.getTypeCode(), request.ext());
        // 暂存附件绑定到正式需求
        attachmentService.rebind(request.attachmentIds(), "DEMAND", demand.getId());
        // 状态机：DRAFT → SUBMITTED（写流转日志 + 发布领域事件）
        stateMachine.transition(demand.getId(), DemandEvent.SUBMIT, user, TransitionContext.of("提交需求"));
        // 草稿转化标记
        draftService.markConverted(draft, demand.getId());
        return demandMapper.selectById(demand.getId());
    }

    /** 提报人撤销（FR-M2-07）：仅 SUBMITTED 可撤，原因必填，关闭留痕 */
    @Transactional(rollbackFor = Exception.class)
    public void withdraw(Long demandId, String reason) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(reason)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "撤销原因必填");
        }
        DemandEntity demand = requireVisible(demandId);
        if (!user.getId().equals(demand.getSubmitterId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅提报人可撤销");
        }
        stateMachine.transition(demandId, DemandEvent.WITHDRAW, user,
                TransitionContext.of(reason.trim()).withUpdater(d -> {
                    d.setClosedAt(LocalDateTime.now());
                    d.setCloseReason("提报人撤销：" + reason.trim());
                }));
    }

    /** 退回补充后重新提交（FR-M3-02）：NEED_INFO → SUBMITTED，可同时更新字段/扩展/附件 */
    @Transactional(rollbackFor = Exception.class)
    public DemandEntity resubmit(Long demandId, ResubmitRequest request) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        if (!user.getId().equals(demand.getSubmitterId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅提报人可补充提交");
        }
        stateMachine.transition(demandId, DemandEvent.SUBMIT, user,
                TransitionContext.of("补充后重新提交").withUpdater(d -> {
                    if (StringUtils.hasText(request.title())) {
                        d.setTitle(request.title().trim());
                    }
                    if (StringUtils.hasText(request.content())) {
                        d.setContent(request.content());
                    }
                    if (StringUtils.hasText(request.urgency())) {
                        d.setUrgency(request.urgency());
                    }
                    if (request.expectDeliveryAt() != null) {
                        d.setExpectDeliveryAt(request.expectDeliveryAt());
                    }
                }));
        extService.patchExt(demandId, demand.getDemandTypeCode(), request.ext());
        attachmentService.rebind(request.attachmentIds(), "DEMAND", demandId);
        return demandMapper.selectById(demandId);
    }

    private DemandTypeEntity requireActiveType(String typeCode) {
        if (!StringUtils.hasText(typeCode)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "需求类型不能为空");
        }
        DemandTypeEntity type = demandTypeMapper.selectOne(new LambdaQueryWrapper<DemandTypeEntity>()
                .eq(DemandTypeEntity::getTypeCode, typeCode)
                .eq(DemandTypeEntity::getStatus, "ACTIVE"));
        if (type == null) {
            throw new BizException(ErrorCode.DEMAND_TYPE_INVALID, "需求类型不存在或已停用: " + typeCode);
        }
        return type;
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

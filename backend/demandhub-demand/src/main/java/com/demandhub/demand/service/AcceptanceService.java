package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.AcceptanceReviewRequest;
import com.demandhub.demand.entity.AssignmentEntity;
import com.demandhub.demand.entity.AttachmentEntity;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.EffortLogEntity;
import com.demandhub.demand.entity.ReviewEntity;
import com.demandhub.demand.entity.SolutionEntity;
import com.demandhub.demand.mapper.AssignmentMapper;
import com.demandhub.demand.mapper.AttachmentMapper;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.EffortLogMapper;
import com.demandhub.demand.mapper.ReviewMapper;
import com.demandhub.demand.mapper.SolutionMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * M5 验收与归档：提交验收（前置校验）/ 验收通过（评分 + 归档）/ 验收打回。
 */
@Service
public class AcceptanceService {

    private final DemandMapper demandMapper;
    private final SolutionMapper solutionMapper;
    private final EffortLogMapper effortLogMapper;
    private final AttachmentMapper attachmentMapper;
    private final ReviewMapper reviewMapper;
    private final AssignmentMapper assignmentMapper;
    private final DemandStateMachine stateMachine;

    public AcceptanceService(DemandMapper demandMapper, SolutionMapper solutionMapper,
                             EffortLogMapper effortLogMapper, AttachmentMapper attachmentMapper,
                             ReviewMapper reviewMapper, AssignmentMapper assignmentMapper,
                             DemandStateMachine stateMachine) {
        this.demandMapper = demandMapper;
        this.solutionMapper = solutionMapper;
        this.effortLogMapper = effortLogMapper;
        this.attachmentMapper = attachmentMapper;
        this.reviewMapper = reviewMapper;
        this.assignmentMapper = assignmentMapper;
        this.stateMachine = stateMachine;
    }

    /** 提交验收（FR-M5-01）：IN_PROGRESS → ACCEPTANCE，前置校验方案已确认/工时已填/交付物已传 */
    @Transactional(rollbackFor = Exception.class)
    public void submitAcceptance(Long demandId) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        if (!user.getId().equals(demand.getAssigneeUserId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅当前处理人可提交验收");
        }
        List<String> missing = new ArrayList<>();
        Long approved = solutionMapper.selectCount(new LambdaQueryWrapper<SolutionEntity>()
                .eq(SolutionEntity::getDemandId, demandId)
                .eq(SolutionEntity::getStatus, "APPROVED"));
        if (approved == 0) {
            missing.add("方案未确认");
        }
        Long efforts = effortLogMapper.selectCount(new LambdaQueryWrapper<EffortLogEntity>()
                .eq(EffortLogEntity::getDemandId, demandId));
        if (efforts == 0) {
            missing.add("工时未填报");
        }
        Long deliverables = attachmentMapper.selectCount(new LambdaQueryWrapper<AttachmentEntity>()
                .eq(AttachmentEntity::getBizType, "DEMAND")
                .eq(AttachmentEntity::getBizId, demandId));
        if (deliverables == 0) {
            missing.add("交付物未上传");
        }
        if (!missing.isEmpty()) {
            throw new BizException(ErrorCode.ACCEPTANCE_PRECONDITION, String.join("、", missing));
        }
        stateMachine.transition(demandId, DemandEvent.SUBMIT_ACCEPTANCE, user, TransitionContext.of("提交验收"));
    }

    /**
     * 验收结论（FR-M5-02/03）：提报人（或实际需求人）操作。
     * PASS → DONE（质量+满意度评分，归档实际交付时间）；REJECT → IN_PROGRESS（意见必填）。
     */
    @Transactional(rollbackFor = Exception.class)
    public void review(Long demandId, AcceptanceReviewRequest request) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        boolean isDemander = user.getId().equals(demand.getSubmitterId())
                || user.getId().equals(demand.getActualDemanderId());
        if (!isDemander) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅提报人可验收");
        }
        boolean pass = "PASS".equals(request.conclusion());
        if (!pass && !"REJECT".equals(request.conclusion())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "验收结论必须为 PASS 或 REJECT");
        }
        if (pass) {
            if (request.qualityScore() == null || request.qualityScore() < 1 || request.qualityScore() > 5
                    || request.satisfactionScore() == null || request.satisfactionScore() < 1
                    || request.satisfactionScore() > 5) {
                throw new BizException(ErrorCode.PARAM_INVALID, "验收通过需填写 1-5 星质量评分与满意度评分");
            }
        } else if (!StringUtils.hasText(request.comment())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "验收打回意见必填");
        }

        LocalDateTime now = LocalDateTime.now();
        stateMachine.transition(demandId, pass ? DemandEvent.ACCEPT_PASS : DemandEvent.ACCEPT_REJECT, user,
                TransitionContext.of(request.comment()).withUpdater(d -> {
                    if (pass) {
                        d.setQualityScore(request.qualityScore());
                        d.setSatisfactionScore(request.satisfactionScore());
                        d.setActualDeliveryAt(now);
                    }
                }));

        ReviewEntity review = new ReviewEntity();
        review.setDemandId(demandId);
        review.setReviewType("ACCEPTANCE");
        review.setReviewerId(user.getId());
        review.setConclusion(request.conclusion());
        review.setQualityScore(request.qualityScore());
        review.setComment(request.comment());
        review.setReviewedAt(now);
        reviewMapper.insert(review);

        // 归档/打回同步处理任务状态
        assignmentMapper.update(null, new LambdaUpdateWrapper<AssignmentEntity>()
                .eq(AssignmentEntity::getDemandId, demandId)
                .eq(AssignmentEntity::getStatus, "PROCESSING")
                .set(AssignmentEntity::getStatus, pass ? "DONE" : "PROCESSING")
                .set(pass, AssignmentEntity::getFinishedAt, now));
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

package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.SolutionReviewRequest;
import com.demandhub.demand.dto.SolutionSaveRequest;
import com.demandhub.demand.dto.SolutionUpdateRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.ReviewEntity;
import com.demandhub.demand.entity.SolutionEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.ReviewMapper;
import com.demandhub.demand.mapper.SolutionMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;

/**
 * M4 方案协作（FR-M4-02/03）：多版本（版本号递增）、提交评审、评审通过/打回、版本对比。
 */
@Service
public class SolutionService {

    private final SolutionMapper solutionMapper;
    private final ReviewMapper reviewMapper;
    private final DemandMapper demandMapper;
    private final DemandStateMachine stateMachine;
    private final OrgScopeService orgScopeService;

    public SolutionService(SolutionMapper solutionMapper, ReviewMapper reviewMapper,
                           DemandMapper demandMapper, DemandStateMachine stateMachine,
                           OrgScopeService orgScopeService) {
        this.solutionMapper = solutionMapper;
        this.reviewMapper = reviewMapper;
        this.demandMapper = demandMapper;
        this.stateMachine = stateMachine;
        this.orgScopeService = orgScopeService;
    }

    /** 新建方案版本（处理人，需求 ANALYZING；版本号 = 当前最大 + 1） */
    @Transactional(rollbackFor = Exception.class)
    public SolutionEntity create(SolutionSaveRequest request) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(request.demandId());
        if (!"ANALYZING".equals(demand.getStatus())) {
            throw new BizException(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅分析中可撰写方案");
        }
        requireAssigneeOrManager(user, demand);
        Integer maxVersion = solutionMapper.selectList(new LambdaQueryWrapper<SolutionEntity>()
                        .eq(SolutionEntity::getDemandId, request.demandId())
                        .orderByDesc(SolutionEntity::getVersion)
                        .last("LIMIT 1"))
                .stream().findFirst().map(SolutionEntity::getVersion).orElse(0);
        SolutionEntity solution = new SolutionEntity();
        solution.setDemandId(request.demandId());
        solution.setVersion(maxVersion + 1);
        solution.setAuthorId(user.getId());
        solution.setSpecContent(request.specContent());
        solution.setSolutionContent(request.solutionContent());
        solution.setPlanDeliveryAt(request.planDeliveryAt());
        solution.setStatus("DRAFT");
        solution.setRemark(request.remark());
        solutionMapper.insert(solution);
        return solution;
    }

    /** 更新方案草稿（仅作者、仅 DRAFT） */
    @Transactional(rollbackFor = Exception.class)
    public SolutionEntity update(Long solutionId, SolutionUpdateRequest request) {
        CurrentUser user = requireLogin();
        SolutionEntity solution = requireSolution(solutionId);
        if (!"DRAFT".equals(solution.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "仅草稿状态的方案可编辑");
        }
        if (!user.getId().equals(solution.getAuthorId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅方案作者可编辑");
        }
        solution.setSpecContent(request.specContent());
        solution.setSolutionContent(request.solutionContent());
        solution.setPlanDeliveryAt(request.planDeliveryAt());
        solution.setRemark(request.remark());
        solutionMapper.updateById(solution);
        return solution;
    }

    /** 提交评审：方案 DRAFT → REVIEWING；需求 ANALYZING → SOLUTION_REVIEW */
    @Transactional(rollbackFor = Exception.class)
    public void submitReview(Long solutionId) {
        CurrentUser user = requireLogin();
        SolutionEntity solution = requireSolution(solutionId);
        if (!"DRAFT".equals(solution.getStatus()) && !"REJECTED".equals(solution.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "当前方案状态不可提交评审");
        }
        DemandEntity demand = requireVisible(solution.getDemandId());
        requireAssigneeOrManager(user, demand);
        Long reviewing = solutionMapper.selectCount(new LambdaQueryWrapper<SolutionEntity>()
                .eq(SolutionEntity::getDemandId, solution.getDemandId())
                .eq(SolutionEntity::getStatus, "REVIEWING"));
        if (reviewing > 0) {
            throw new BizException(ErrorCode.BIZ_ERROR, "已有方案在评审中，请先完成评审");
        }
        stateMachine.transition(solution.getDemandId(), DemandEvent.SUBMIT_REVIEW, user,
                TransitionContext.of("提交方案评审").putExtra("solutionId", solutionId)
                        .putExtra("version", solution.getVersion()));
        solution.setStatus("REVIEWING");
        solutionMapper.updateById(solution);
    }

    /** 方案评审（经理）：PASS → CONFIRMED（落计划交付时间）；REJECT → ANALYZING（意见必填） */
    @Transactional(rollbackFor = Exception.class)
    public void review(Long solutionId, SolutionReviewRequest request) {
        CurrentUser user = requireLogin();
        SolutionEntity solution = requireSolution(solutionId);
        if (!"REVIEWING".equals(solution.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "方案不在评审中");
        }
        boolean pass = "PASS".equals(request.conclusion());
        if (!pass && !"REJECT".equals(request.conclusion())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "评审结论必须为 PASS 或 REJECT");
        }
        if (!pass && !StringUtils.hasText(request.comment())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "打回意见必填");
        }
        DemandEntity demand = requireVisible(solution.getDemandId());
        // 评审双重命中：类型集合 × 组织子树均为本需求方可评审
        orgScopeService.requireManage(user, demand.getAssigneeOrgId(), demand.getDemandTypeCode());
        stateMachine.transition(solution.getDemandId(), pass ? DemandEvent.REVIEW_PASS : DemandEvent.REVIEW_REJECT,
                user, TransitionContext.of(request.comment())
                        .putExtra("solutionId", solutionId)
                        .putExtra("version", solution.getVersion())
                        .withUpdater(d -> {
                            if (pass && solution.getPlanDeliveryAt() != null) {
                                d.setExpectDeliveryAt(solution.getPlanDeliveryAt());
                            }
                        }));
        solution.setStatus(pass ? "APPROVED" : "REJECTED");
        solutionMapper.updateById(solution);

        ReviewEntity review = new ReviewEntity();
        review.setDemandId(solution.getDemandId());
        review.setSolutionId(solutionId);
        review.setReviewType("SOLUTION");
        review.setReviewerId(user.getId());
        review.setConclusion(request.conclusion());
        review.setComment(request.comment());
        review.setReviewedAt(LocalDateTime.now());
        reviewMapper.insert(review);
    }

    public List<SolutionEntity> listByDemand(Long demandId) {
        requireVisible(demandId);
        return solutionMapper.selectList(new LambdaQueryWrapper<SolutionEntity>()
                .eq(SolutionEntity::getDemandId, demandId)
                .orderByDesc(SolutionEntity::getVersion));
    }

    /** 版本对比：返回两个版本完整内容，前端做 diff */
    public List<SolutionEntity> compare(Long demandId, Integer v1, Integer v2) {
        requireVisible(demandId);
        List<SolutionEntity> list = solutionMapper.selectList(new LambdaQueryWrapper<SolutionEntity>()
                .eq(SolutionEntity::getDemandId, demandId)
                .in(SolutionEntity::getVersion, v1, v2)
                .orderByAsc(SolutionEntity::getVersion));
        if (list.size() != 2) {
            throw new BizException(ErrorCode.SOLUTION_NOT_FOUND, "对比的版本不存在");
        }
        return list;
    }

    public List<ReviewEntity> listReviews(Long demandId, String reviewType) {
        requireVisible(demandId);
        return reviewMapper.selectList(new LambdaQueryWrapper<ReviewEntity>()
                .eq(ReviewEntity::getDemandId, demandId)
                .eq(StringUtils.hasText(reviewType), ReviewEntity::getReviewType, reviewType)
                .orderByAsc(ReviewEntity::getId));
    }

    private void requireAssigneeOrManager(CurrentUser user, DemandEntity demand) {
        if (user.getId().equals(demand.getAssigneeUserId())) {
            return;
        }
        if (orgScopeService.canManage(user, demand.getAssigneeOrgId(), demand.getDemandTypeCode())) {
            return;
        }
        throw new BizException(ErrorCode.FORBIDDEN, "仅当前处理人或本类型本组织经理可操作");
    }

    private SolutionEntity requireSolution(Long solutionId) {
        SolutionEntity solution = solutionMapper.selectById(solutionId);
        if (solution == null) {
            throw new BizException(ErrorCode.SOLUTION_NOT_FOUND);
        }
        return solution;
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

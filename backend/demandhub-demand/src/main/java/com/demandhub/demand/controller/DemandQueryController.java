package com.demandhub.demand.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.DemandDetailVO;
import com.demandhub.demand.dto.DemandListItemVO;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.service.ActionPolicyService;
import com.demandhub.demand.service.AttachmentService;
import com.demandhub.demand.service.DemandExtService;
import com.demandhub.demand.service.OrgLookupService;
import com.demandhub.demand.service.UserLookupService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.BeanUtils;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 需求查询（M2~M5）：列表自动按当前用户数据范围过滤（数据权限拦截器），
 * 详情拼装扩展表 + 姓名/组织 + 附件 + 当前用户可用操作列表。
 */
@Tag(name = "需求查询")
@RestController
@RequestMapping("/demand/demand")
public class DemandQueryController {

    private final DemandMapper demandMapper;
    private final DemandTransitionLogMapper transitionLogMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final DemandExtService extService;
    private final AttachmentService attachmentService;
    private final UserLookupService userLookupService;
    private final OrgLookupService orgLookupService;
    private final ActionPolicyService actionPolicyService;

    public DemandQueryController(DemandMapper demandMapper, DemandTransitionLogMapper transitionLogMapper,
                                 DemandTypeMapper demandTypeMapper, DemandExtService extService,
                                 AttachmentService attachmentService, UserLookupService userLookupService,
                                 OrgLookupService orgLookupService, ActionPolicyService actionPolicyService) {
        this.demandMapper = demandMapper;
        this.transitionLogMapper = transitionLogMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.extService = extService;
        this.attachmentService = attachmentService;
        this.userLookupService = userLookupService;
        this.orgLookupService = orgLookupService;
        this.actionPolicyService = actionPolicyService;
    }

    @Operation(summary = "需求分页（数据权限过滤；mine=true 仅看我提的/代提的）")
    @GetMapping("/page")
    public Result<Page<DemandListItemVO>> page(@RequestParam(defaultValue = "1") long current,
                                               @RequestParam(defaultValue = "10") long size,
                                               @RequestParam(required = false) String status,
                                               @RequestParam(required = false) String demandTypeCode,
                                               @RequestParam(required = false) String channel,
                                               @RequestParam(required = false) String urgency,
                                               @RequestParam(required = false) String keyword,
                                               @RequestParam(required = false) Integer onHold,
                                               @RequestParam(defaultValue = "false") boolean mine,
                                               @RequestParam(defaultValue = "desc") String submittedOrder) {
        LambdaQueryWrapper<DemandEntity> wrapper = new LambdaQueryWrapper<DemandEntity>()
                .eq(StringUtils.hasText(status), DemandEntity::getStatus, status)
                .eq(StringUtils.hasText(demandTypeCode), DemandEntity::getDemandTypeCode, demandTypeCode)
                .eq(StringUtils.hasText(channel), DemandEntity::getChannel, channel)
                .eq(StringUtils.hasText(urgency), DemandEntity::getUrgency, urgency)
                .eq(onHold != null, DemandEntity::getOnHold, onHold)
                .and(StringUtils.hasText(keyword), w -> w.like(DemandEntity::getTitle, keyword)
                        .or().like(DemandEntity::getDemandNo, keyword))
                .and(mine, w -> w.eq(DemandEntity::getSubmitterId, UserContext.currentUserId())
                        .or().eq(DemandEntity::getActualDemanderId, UserContext.currentUserId()));
        // 提交时间排序（默认倒序）；同刻记录按 id 次序兜底，保证跨页顺序稳定
        boolean asc = "asc".equalsIgnoreCase(submittedOrder);
        wrapper.orderBy(true, asc, DemandEntity::getSubmittedAt)
                .orderBy(true, asc, DemandEntity::getId);
        Page<DemandEntity> page = demandMapper.selectPage(new Page<>(current, size), wrapper);

        // 批量拼装姓名/组织/类型名
        Set<Long> userIds = new HashSet<>();
        Set<Long> orgIds = new HashSet<>();
        page.getRecords().forEach(d -> {
            userIds.add(d.getSubmitterId());
            if (d.getAssigneeUserId() != null) {
                userIds.add(d.getAssigneeUserId());
            }
            if (d.getAssigneeOrgId() != null) {
                orgIds.add(d.getAssigneeOrgId());
            }
        });
        Map<Long, String> userNames = userLookupService.namesOf(userIds);
        Map<Long, String> orgNames = orgLookupService.namesOf(orgIds);
        Map<String, String> typeNames = demandTypeMapper.selectList(null).stream()
                .collect(Collectors.toMap(DemandTypeEntity::getTypeCode, DemandTypeEntity::getTypeName, (a, b) -> a));

        Page<DemandListItemVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(page.getRecords().stream().map(d -> {
            DemandListItemVO vo = new DemandListItemVO();
            BeanUtils.copyProperties(d, vo);
            vo.setSubmitterName(userNames.get(d.getSubmitterId()));
            vo.setAssigneeUserName(userNames.get(d.getAssigneeUserId()));
            vo.setAssigneeOrgName(orgNames.get(d.getAssigneeOrgId()));
            vo.setTypeName(typeNames.get(d.getDemandTypeCode()));
            return vo;
        }).collect(Collectors.toList()));
        return Result.ok(voPage);
    }

    @Operation(summary = "需求详情（扩展表 + 附件 + 可用操作；越权返回 403）")
    @GetMapping("/{id}")
    public Result<DemandDetailVO> detail(@PathVariable Long id) {
        // 数据权限拦截器已追加范围条件：查不到即越权（NFR-08 返回 403）
        DemandEntity demand = demandMapper.selectById(id);
        if (demand == null) {
            throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该需求");
        }
        DemandDetailVO vo = new DemandDetailVO();
        vo.setDemand(demand);
        vo.setExt(extService.readExt(id, demand.getDemandTypeCode()));
        DemandTypeEntity type = demandTypeMapper.selectOne(new LambdaQueryWrapper<DemandTypeEntity>()
                .eq(DemandTypeEntity::getTypeCode, demand.getDemandTypeCode()));
        vo.setTypeName(type == null ? demand.getDemandTypeCode() : type.getTypeName());
        vo.setSubmitterName(userLookupService.nameOf(demand.getSubmitterId()));
        vo.setActualDemanderName(userLookupService.nameOf(demand.getActualDemanderId()));
        vo.setAssigneeOrgName(orgLookupService.nameOf(demand.getAssigneeOrgId()));
        vo.setAssigneeUserName(userLookupService.nameOf(demand.getAssigneeUserId()));
        vo.setAttachments(attachmentService.listByBiz("DEMAND", id));
        vo.setAvailableActions(actionPolicyService.availableActions(demand, UserContext.get()));
        if (demand.getOnHold() != null && demand.getOnHold() == 1) {
            DemandTransitionLogEntity lastHold = transitionLogMapper.selectOne(new LambdaQueryWrapper<DemandTransitionLogEntity>()
                    .eq(DemandTransitionLogEntity::getDemandId, id)
                    .eq(DemandTransitionLogEntity::getAction, "HOLD")
                    .orderByDesc(DemandTransitionLogEntity::getId)
                    .last("LIMIT 1"));
            if (lastHold != null) {
                vo.setHoldDays(Duration.between(lastHold.getCreatedAt(), LocalDateTime.now()).toDays());
            }
        }
        return Result.ok(vo);
    }

    @Operation(summary = "流转日志（按时间升序）")
    @GetMapping("/{id}/transitions")
    public Result<List<DemandTransitionLogEntity>> transitions(@PathVariable Long id) {
        DemandEntity demand = demandMapper.selectById(id);
        if (demand == null) {
            throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该需求");
        }
        return Result.ok(transitionLogMapper.selectList(new LambdaQueryWrapper<DemandTransitionLogEntity>()
                .eq(DemandTransitionLogEntity::getDemandId, id)
                .orderByAsc(DemandTransitionLogEntity::getId)));
    }
}

package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.EffortAddRequest;
import com.demandhub.demand.dto.EffortUpdateRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.EffortLogEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.EffortLogMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * M4 工时记录（FR-M4-05）：按日填报，按人/按日汇总；已完成需求的历史工时不可修改。
 */
@Service
public class EffortService {

    private final EffortLogMapper effortLogMapper;
    private final DemandMapper demandMapper;

    public EffortService(EffortLogMapper effortLogMapper, DemandMapper demandMapper) {
        this.effortLogMapper = effortLogMapper;
        this.demandMapper = demandMapper;
    }

    @Transactional(rollbackFor = Exception.class)
    public EffortLogEntity add(EffortAddRequest request) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(request.demandId());
        if (demand.getStatus().equals("DONE") || demand.getStatus().equals("CLOSED")) {
            throw new BizException(ErrorCode.BIZ_ERROR, "需求已结束，不可再填报工时");
        }
        validate(request.workDate(), request.hours());
        EffortLogEntity effort = new EffortLogEntity();
        effort.setDemandId(request.demandId());
        effort.setUserId(user.getId());
        effort.setWorkDate(request.workDate());
        effort.setHours(request.hours());
        effort.setDescription(request.description());
        effortLogMapper.insert(effort);
        return effort;
    }

    /** 修改工时（仅本人记录；已完成需求的历史工时不可修改 —— FR-M4-05） */
    @Transactional(rollbackFor = Exception.class)
    public EffortLogEntity update(Long effortId, EffortUpdateRequest request) {
        CurrentUser user = requireLogin();
        EffortLogEntity effort = effortLogMapper.selectById(effortId);
        if (effort == null) {
            throw new BizException(ErrorCode.EFFORT_NOT_FOUND);
        }
        if (!user.getId().equals(effort.getUserId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅本人可修改工时记录");
        }
        DemandEntity demand = requireVisible(effort.getDemandId());
        if ("DONE".equals(demand.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "需求已完成，历史工时不可修改（可追加更正记录）");
        }
        validate(request.workDate(), request.hours());
        effort.setWorkDate(request.workDate());
        effort.setHours(request.hours());
        effort.setDescription(request.description());
        effortLogMapper.updateById(effort);
        return effort;
    }

    public List<EffortLogEntity> listByDemand(Long demandId) {
        requireVisible(demandId);
        return effortLogMapper.selectList(new LambdaQueryWrapper<EffortLogEntity>()
                .eq(EffortLogEntity::getDemandId, demandId)
                .orderByAsc(EffortLogEntity::getWorkDate)
                .orderByAsc(EffortLogEntity::getId));
    }

    /** 汇总：按人 + 按日 + 总计 */
    public Map<String, Object> summary(Long demandId) {
        List<EffortLogEntity> list = listByDemand(demandId);
        Map<Long, BigDecimal> byUser = new LinkedHashMap<>();
        Map<LocalDate, BigDecimal> byDate = new LinkedHashMap<>();
        BigDecimal total = BigDecimal.ZERO;
        for (EffortLogEntity e : list) {
            byUser.merge(e.getUserId(), e.getHours(), BigDecimal::add);
            byDate.merge(e.getWorkDate(), e.getHours(), BigDecimal::add);
            total = total.add(e.getHours());
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("totalHours", total);
        result.put("byUser", byUser.entrySet().stream()
                .map(en -> Map.of("userId", en.getKey(), "hours", en.getValue())).collect(Collectors.toList()));
        result.put("byDate", byDate.entrySet().stream()
                .map(en -> Map.of("workDate", en.getKey(), "hours", en.getValue())).collect(Collectors.toList()));
        return result;
    }

    private void validate(LocalDate workDate, BigDecimal hours) {
        if (workDate == null) {
            throw new BizException(ErrorCode.PARAM_INVALID, "工作日期不能为空");
        }
        if (hours == null || hours.compareTo(BigDecimal.ZERO) <= 0
                || hours.compareTo(new BigDecimal("24")) > 0) {
            throw new BizException(ErrorCode.PARAM_INVALID, "工时小时数需在 0-24 之间");
        }
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

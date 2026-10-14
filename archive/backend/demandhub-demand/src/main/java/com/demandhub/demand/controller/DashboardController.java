package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.ManagerBoardVO;
import com.demandhub.demand.dto.OrgBoardVO;
import com.demandhub.demand.service.DashboardService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 看板报表（M6，FR-M6-01/02）：管理者看板（全线/授权子树）+ 经理看板（本组织）。
 * 数据范围由 DataScopeInterceptor 自动注入，口径与列表页一致。
 */
@Tag(name = "看板报表")
@RestController
@RequestMapping("/demand/dashboard")
public class DashboardController {

    private final DashboardService dashboardService;

    public DashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @Operation(summary = "管理者看板（KPI + 近12周趋势 + 类型分布 + 渠道分布 + 组织积压TopN + SLA健康度）")
    @GetMapping("/manager")
    @RequireRole({"EXECUTIVE", "MANAGER"})
    public Result<ManagerBoardVO> managerBoard(
            @RequestParam(defaultValue = "month") String range,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to) {
        return Result.ok(dashboardService.managerBoard(range, from, to));
    }

    @Operation(summary = "经理看板（本类型本组织：待受理/池中/处理中/本周完成/人均在途/成员工作量）")
    @GetMapping("/org")
    @RequireRole({"MANAGER", "EXECUTIVE"})
    public Result<OrgBoardVO> orgBoard() {
        return Result.ok(dashboardService.orgBoard());
    }

    @Operation(summary = "手动触发预聚合刷新（检查点 3：立即刷新 demand_stat_daily 当日快照）")
    @PostMapping("/stat-refresh")
    @RequireRole({"ADMIN", "EXECUTIVE"})
    public Result<Map<String, Object>> statRefresh() {
        int rows = dashboardService.refreshStatDaily();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("affectedRows", rows);
        return Result.ok(data);
    }
}

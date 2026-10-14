package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.EffortAddRequest;
import com.demandhub.demand.dto.EffortUpdateRequest;
import com.demandhub.demand.entity.EffortLogEntity;
import com.demandhub.demand.service.EffortService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * M4 工时记录：按日填报，按人/按日/按需求汇总；已完成需求历史工时不可修改。
 */
@Tag(name = "工时记录")
@RestController
@RequestMapping("/demand/effort")
public class EffortController {

    private final EffortService effortService;

    public EffortController(EffortService effortService) {
        this.effortService = effortService;
    }

    @Operation(summary = "填报工时")
    @PostMapping
    public Result<EffortLogEntity> add(@RequestBody EffortAddRequest request) {
        return Result.ok(effortService.add(request));
    }

    @Operation(summary = "修改工时（仅本人；已完成需求不可改）")
    @PutMapping("/{id}")
    public Result<EffortLogEntity> update(@PathVariable Long id, @RequestBody EffortUpdateRequest request) {
        return Result.ok(effortService.update(id, request));
    }

    @Operation(summary = "工时列表（按日升序）")
    @GetMapping("/list")
    public Result<List<EffortLogEntity>> list(@RequestParam Long demandId) {
        return Result.ok(effortService.listByDemand(demandId));
    }

    @Operation(summary = "工时汇总（按人 + 按日 + 总计）")
    @GetMapping("/summary")
    public Result<Map<String, Object>> summary(@RequestParam Long demandId) {
        return Result.ok(effortService.summary(demandId));
    }
}

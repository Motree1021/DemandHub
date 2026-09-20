package com.demandhub.demand.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.mapper.DemandMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 需求查询（阶段 2 最小实现，用于数据权限过滤与越权用例自测；完整提报/流转见 M2+）
 */
@Tag(name = "需求查询")
@RestController
@RequestMapping("/demand/demand")
public class DemandQueryController {

    private final DemandMapper demandMapper;

    public DemandQueryController(DemandMapper demandMapper) {
        this.demandMapper = demandMapper;
    }

    @Operation(summary = "需求分页（自动按当前用户数据范围过滤）")
    @GetMapping("/page")
    public Result<Page<DemandEntity>> page(@RequestParam(defaultValue = "1") long current,
                                           @RequestParam(defaultValue = "10") long size,
                                           @RequestParam(required = false) String status) {
        return Result.ok(demandMapper.selectPage(new Page<>(current, size),
                new LambdaQueryWrapper<DemandEntity>()
                        .eq(StringUtils.hasText(status), DemandEntity::getStatus, status)
                        .orderByDesc(DemandEntity::getId)));
    }

    @Operation(summary = "需求详情（越权返回 403）")
    @GetMapping("/{id}")
    public Result<DemandEntity> detail(@PathVariable Long id) {
        // 数据权限拦截器已追加范围条件：查不到即越权（NFR-08 返回 403）
        DemandEntity demand = demandMapper.selectById(id);
        if (demand == null) {
            throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该需求");
        }
        return Result.ok(demand);
    }
}

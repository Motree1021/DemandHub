package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.SysDictEntity;
import com.demandhub.demand.service.SysDictAdminService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 字典下拉项查询（登录用户可用，供表单下拉；管理维护走 /demand/admin/dicts）。
 */
@Tag(name = "字典下拉")
@RestController
@RequestMapping("/demand/dicts")
public class DictQueryController {

    private final SysDictAdminService dictService;

    public DictQueryController(SysDictAdminService dictService) {
        this.dictService = dictService;
    }

    @Operation(summary = "按分组查启用字典项（如 URGENCY/CLOSE_REASON/HOLD_REASON）")
    @GetMapping
    public Result<List<SysDictEntity>> listActive(@RequestParam String dictType) {
        return Result.ok(dictService.listActive(dictType));
    }
}

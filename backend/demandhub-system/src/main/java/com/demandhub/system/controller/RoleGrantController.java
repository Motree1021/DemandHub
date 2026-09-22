package com.demandhub.system.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.Result;
import com.demandhub.system.dto.RoleGrantSaveRequest;
import com.demandhub.system.entity.RoleGrant;
import com.demandhub.system.service.RoleGrantService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 业务角色授权管理（FR-M1-03）：仅系统管理员。
 */
@Tag(name = "业务角色授权")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/system/grant")
public class RoleGrantController {

    private final RoleGrantService roleGrantService;

    public RoleGrantController(RoleGrantService roleGrantService) {
        this.roleGrantService = roleGrantService;
    }

    @Operation(summary = "授权分页查询")
    @GetMapping("/page")
    public Result<Page<RoleGrant>> page(@RequestParam(defaultValue = "1") long current,
                                        @RequestParam(defaultValue = "10") long size,
                                        @RequestParam(required = false) Long demandUserId,
                                        @RequestParam(required = false) String roleCode) {
        return Result.ok(roleGrantService.page(current, size, demandUserId, roleCode));
    }

    @Operation(summary = "新增授权")
    @PostMapping
    public Result<Long> create(@Valid @RequestBody RoleGrantSaveRequest request) {
        Long grantedBy = UserContext.get() != null ? UserContext.get().getId() : null;
        return Result.ok(roleGrantService.create(request, grantedBy));
    }

    @Operation(summary = "修改授权")
    @PutMapping("/{id}")
    public Result<Void> update(@PathVariable Long id, @Valid @RequestBody RoleGrantSaveRequest request) {
        request.setId(id);
        roleGrantService.update(request);
        return Result.ok();
    }

    @Operation(summary = "删除授权")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        roleGrantService.delete(id);
        return Result.ok();
    }
}

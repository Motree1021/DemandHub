package com.demandhub.system.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.system.dto.ChannelConfigRequest;
import com.demandhub.system.dto.ChannelVO;
import com.demandhub.system.entity.ChannelDeptUnmapped;
import com.demandhub.system.service.ChannelService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.Serializable;
import java.util.List;

/**
 * 渠道管理（FR-M1-04，P4 管理端）：列表（密钥脱敏）/启停/配置更新（密钥加密落库）/连接测试/
 * 部门未映射校准清单。仅系统管理员。
 */
@Tag(name = "渠道管理")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/system/channel")
public class ChannelController {

    private final ChannelService channelService;

    public ChannelController(ChannelService channelService) {
        this.channelService = channelService;
    }

    @Operation(summary = "渠道列表（config 拍平展示，app_secret 脱敏为 ***）")
    @GetMapping("/list")
    public Result<List<ChannelVO>> list() {
        return Result.ok(channelService.list());
    }

    @Operation(summary = "渠道启停（ACTIVE/DISABLED）")
    @PutMapping("/{id}/status")
    public Result<Void> updateStatus(@PathVariable Long id, @Valid @RequestBody StatusRequest request) {
        channelService.updateStatus(id, request.getStatus());
        return Result.ok();
    }

    @Operation(summary = "更新 SSO 配置（appSecret 留空=不更换；非空加密落库）")
    @PutMapping("/{id}/config")
    public Result<Void> updateConfig(@PathVariable Long id, @RequestBody ChannelConfigRequest request) {
        channelService.updateConfig(id, request);
        return Result.ok();
    }

    @Operation(summary = "连接测试（dummy 票据探活上游 verify，无副作用）")
    @PostMapping("/{id}/test")
    public Result<String> test(@PathVariable Long id) {
        return Result.ok(channelService.testConnection(id));
    }

    @Operation(summary = "部门未映射校准清单分页")
    @GetMapping("/dept-unmapped/page")
    public Result<Page<ChannelDeptUnmapped>> unmappedPage(@RequestParam(defaultValue = "1") long current,
                                                          @RequestParam(defaultValue = "10") long size,
                                                          @RequestParam(required = false) String channelCode) {
        return Result.ok(channelService.unmappedPage(current, size, channelCode));
    }

    @Operation(summary = "删除校准记录（组织 external_dept_id 维护完成后清理）")
    @DeleteMapping("/dept-unmapped/{id}")
    public Result<Void> deleteUnmapped(@PathVariable Long id) {
        channelService.deleteUnmapped(id);
        return Result.ok();
    }

    @Data
    public static class StatusRequest implements Serializable {
        @NotBlank(message = "状态不能为空")
        @Pattern(regexp = "ACTIVE|DISABLED", message = "非法渠道状态")
        private String status;
    }
}

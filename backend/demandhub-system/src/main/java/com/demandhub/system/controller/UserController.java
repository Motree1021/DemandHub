package com.demandhub.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.MaskUtil;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.LoginAccountRequest;
import com.demandhub.system.dto.ResetPasswordRequest;
import com.demandhub.system.dto.UserCompleteRequest;
import com.demandhub.system.dto.UserMergeRequest;
import com.demandhub.system.entity.ChannelUserMapping;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelUserMappingMapper;
import com.demandhub.system.service.UserMergeService;
import com.demandhub.system.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.crypto.bcrypt.BCrypt;
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
 * 用户管理（仅 ADMIN，FR-M1-01）：
 * 分页/详情/补全/激活/停用/合并/渠道映射/设登录账号/重置密码。
 * 出参统一脱敏（手机/邮箱掩码，密码哈希不回显）。
 */
@Tag(name = "用户管理")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/system/user")
public class UserController {

    private final UserService userService;
    private final UserMergeService userMergeService;
    private final ChannelUserMappingMapper mappingMapper;

    public UserController(UserService userService, UserMergeService userMergeService,
                          ChannelUserMappingMapper mappingMapper) {
        this.userService = userService;
        this.userMergeService = userMergeService;
        this.mappingMapper = mappingMapper;
    }

    @Operation(summary = "用户分页（关键字匹配姓名/登录账号/工号；status 精确过滤）")
    @GetMapping("/page")
    public Result<Page<UserSnapshot>> page(@RequestParam(defaultValue = "1") long current,
                                           @RequestParam(defaultValue = "10") long size,
                                           @RequestParam(required = false) String keyword,
                                           @RequestParam(required = false) String status) {
        Page<UserSnapshot> page = userService.page(current, size, keyword, status);
        page.getRecords().forEach(this::mask);
        return Result.ok(page);
    }

    @Operation(summary = "用户详情（含部门路径）")
    @GetMapping("/{id}")
    public Result<UserSnapshot> detail(@PathVariable Long id) {
        return Result.ok(mask(userService.detail(id)));
    }

    @Operation(summary = "资料补全并激活（仅 PENDING 用户，渠道自动建号字段缺失场景）")
    @PostMapping("/{id}/complete")
    public Result<Void> complete(@PathVariable Long id, @Valid @RequestBody UserCompleteRequest req) {
        userService.complete(id, req.getName(), req.getPhone(), req.getEmail(), req.getEmployeeNo(), req.getPrimaryOrgId());
        return Result.ok();
    }

    @Operation(summary = "激活用户")
    @PostMapping("/{id}/activate")
    public Result<Void> activate(@PathVariable Long id) {
        userService.changeStatus(id, true);
        return Result.ok();
    }

    @Operation(summary = "停用用户（全清会话立即踢下线；不可停用自己）")
    @PostMapping("/{id}/disable")
    public Result<Void> disable(@PathVariable Long id) {
        CurrentUser current = UserContext.get();
        if (current != null && current.getId().equals(id)) {
            throw new BizException(ErrorCode.BIZ_ERROR, "不可停用当前登录账号");
        }
        userService.changeStatus(id, false);
        return Result.ok();
    }

    @Operation(summary = "合并预览（源用户各业务表引用计数）")
    @GetMapping("/merge/preview")
    public Result<Map<String, Long>> mergePreview(@RequestParam Long sourceUserId) {
        return Result.ok(userMergeService.preview(sourceUserId));
    }

    @Operation(summary = "用户合并（源用户业务引用迁移至目标用户后置 MERGED）")
    @PostMapping("/merge")
    public Result<Void> merge(@Valid @RequestBody UserMergeRequest req) {
        CurrentUser current = UserContext.get();
        userMergeService.merge(req.getSourceUserId(), req.getTargetUserId(), current != null ? current.getId() : null);
        return Result.ok();
    }

    @Operation(summary = "用户的渠道映射列表")
    @GetMapping("/{id}/mappings")
    public Result<List<ChannelUserMapping>> mappings(@PathVariable Long id) {
        return Result.ok(mappingMapper.selectList(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getDemandUserId, id)
                .orderByAsc(ChannelUserMapping::getId)));
    }

    @Operation(summary = "设置 PC 登录账号（唯一性校验）")
    @PutMapping("/{id}/login-account")
    public Result<Void> setLoginAccount(@PathVariable Long id, @Valid @RequestBody LoginAccountRequest req) {
        userService.setLoginAccount(id, req.getLoginName());
        return Result.ok();
    }

    @Operation(summary = "管理员重置密码（强制下次登录改密 + 全清会话）")
    @PutMapping("/{id}/reset-password")
    public Result<Void> resetPassword(@PathVariable Long id, @Valid @RequestBody ResetPasswordRequest req) {
        ensurePasswordRule(req.getNewPassword());
        userService.resetPassword(id, BCrypt.hashpw(req.getNewPassword(), BCrypt.gensalt()));
        return Result.ok();
    }

    /** 密码强度：至少 8 位且包含字母和数字（与 AuthService 口径一致） */
    private void ensurePasswordRule(String password) {
        boolean ok = password != null && password.length() >= 8
                && password.chars().anyMatch(Character::isLetter)
                && password.chars().anyMatch(Character::isDigit);
        if (!ok) {
            throw new BizException(ErrorCode.PASSWORD_RULE_VIOLATION);
        }
    }

    private UserSnapshot mask(UserSnapshot user) {
        if (user != null) {
            user.setPhone(MaskUtil.phone(user.getPhone()));
            user.setEmail(MaskUtil.email(user.getEmail()));
            user.setPasswordHash(null);
        }
        return user;
    }
}

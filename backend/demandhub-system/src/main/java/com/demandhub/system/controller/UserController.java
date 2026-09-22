package com.demandhub.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.MaskUtil;
import com.demandhub.common.core.Result;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.UserSnapshotMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 用户镜像只读查询（主数据来自权限中心，本地无增删改）
 */
@Tag(name = "用户镜像")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/system/user")
public class UserController {

    private final UserSnapshotMapper userMapper;

    public UserController(UserSnapshotMapper userMapper) {
        this.userMapper = userMapper;
    }

    @Operation(summary = "用户分页查询（关键字匹配姓名/登录账号/工号；手机号/邮箱脱敏返回）")
    @GetMapping("/page")
    public Result<Page<UserSnapshot>> page(@RequestParam(defaultValue = "1") long current,
                                           @RequestParam(defaultValue = "10") long size,
                                           @RequestParam(required = false) String keyword) {
        Page<UserSnapshot> page = userMapper.selectPage(new Page<>(current, size), new LambdaQueryWrapper<UserSnapshot>()
                .and(StringUtils.hasText(keyword), w -> w
                        .like(UserSnapshot::getName, keyword)
                        .or().like(UserSnapshot::getLoginName, keyword)
                        .or().like(UserSnapshot::getEmployeeNo, keyword))
                .orderByAsc(UserSnapshot::getId));
        // 敏感字段出参脱敏（NFR 安全）；密码哈希严禁回显
        page.getRecords().forEach(u -> {
            u.setPhone(MaskUtil.phone(u.getPhone()));
            u.setEmail(MaskUtil.email(u.getEmail()));
            u.setPasswordHash(null);
        });
        return Result.ok(page);
    }
}

package com.demandhub.notification.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationEntity;
import com.demandhub.notification.service.NotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 站内信（FR-M7-01）：我的通知列表、未读计数、标记已读/全部已读。
 * 按 receiver_id = 当前登录人过滤，不走数据权限拦截器。
 */
@Tag(name = "通知中心")
@RestController
@RequestMapping("/notification")
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @Operation(summary = "我的通知列表（分页，isRead 可选筛选）")
    @GetMapping("/mine")
    public Result<Page<NotificationEntity>> mine(@RequestParam(defaultValue = "1") long current,
                                                 @RequestParam(defaultValue = "10") long size,
                                                 @RequestParam(required = false) Boolean isRead) {
        return Result.ok(notificationService.listMine(requireLogin().getId(), isRead, current, size));
    }

    @Operation(summary = "未读计数（实时）")
    @GetMapping("/mine/unread-count")
    public Result<Map<String, Long>> unreadCount() {
        return Result.ok(Map.of("count", notificationService.unreadCount(requireLogin().getId())));
    }

    @Operation(summary = "标记已读")
    @PutMapping("/{id}/read")
    public Result<Void> markRead(@PathVariable Long id) {
        notificationService.markRead(id, requireLogin().getId());
        return Result.ok();
    }

    @Operation(summary = "全部已读")
    @PutMapping("/mine/read-all")
    public Result<Map<String, Integer>> markAllRead() {
        return Result.ok(Map.of("updated", notificationService.markAllRead(requireLogin().getId())));
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}

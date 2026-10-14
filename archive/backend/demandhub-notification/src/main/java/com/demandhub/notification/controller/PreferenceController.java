package com.demandhub.notification.controller;

import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationPreferenceEntity;
import com.demandhub.notification.service.NotifyTypes;
import com.demandhub.notification.service.PreferenceService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 通知偏好（FR-M7-03）：用户关闭非关键通知类型；待办提醒 TODO 不可关闭。
 */
@Tag(name = "通知偏好")
@RestController
@RequestMapping("/notification/preferences")
public class PreferenceController {

    private final PreferenceService preferenceService;

    public PreferenceController(PreferenceService preferenceService) {
        this.preferenceService = preferenceService;
    }

    @Operation(summary = "我的偏好列表（全部类型；closable=false 表示关键通知不可关）")
    @GetMapping
    public Result<List<Map<String, Object>>> mine() {
        CurrentUser user = requireLogin();
        Map<String, Boolean> saved = new LinkedHashMap<>();
        for (NotificationPreferenceEntity pref : preferenceService.listMine(user.getId())) {
            saved.put(pref.getNotifyType(), pref.getEnabled() != null && pref.getEnabled() == 1);
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (String type : NotifyTypes.ALL) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("notifyType", type);
            item.put("closable", NotifyTypes.isClosable(type));
            item.put("enabled", NotifyTypes.isClosable(type) ? saved.getOrDefault(type, true) : true);
            result.add(item);
        }
        return Result.ok(result);
    }

    @Operation(summary = "设置某类通知开关（即时生效）")
    @PutMapping
    public Result<Void> update(@RequestBody PreferenceUpdateRequest request) {
        preferenceService.setEnabled(requireLogin().getId(), request.notifyType(), request.enabled());
        return Result.ok();
    }

    public record PreferenceUpdateRequest(String notifyType, Boolean enabled) {
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}

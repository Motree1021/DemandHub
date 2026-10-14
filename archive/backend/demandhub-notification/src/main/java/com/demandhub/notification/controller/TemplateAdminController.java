package com.demandhub.notification.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationTemplateEntity;
import com.demandhub.notification.service.TemplateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 通知模板管理（FR-M8-03，限 ADMIN）：模板 CRUD + 变量渲染预览。
 */
@Tag(name = "系统管理-通知模板")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/notification/admin/templates")
public class TemplateAdminController {

    private final TemplateService templateService;

    public TemplateAdminController(TemplateService templateService) {
        this.templateService = templateService;
    }

    @Operation(summary = "模板列表")
    @GetMapping
    public Result<List<NotificationTemplateEntity>> list() {
        return Result.ok(templateService.list());
    }

    @Operation(summary = "模板详情")
    @GetMapping("/{id}")
    public Result<NotificationTemplateEntity> detail(@PathVariable Long id) {
        return Result.ok(templateService.requireById(id));
    }

    @Operation(summary = "新增模板（编码唯一）")
    @PostMapping
    public Result<NotificationTemplateEntity> create(@RequestBody NotificationTemplateEntity request) {
        return Result.ok(templateService.create(request));
    }

    @Operation(summary = "编辑模板（编码不可改，修改后新消息即时生效）")
    @PutMapping("/{id}")
    public Result<NotificationTemplateEntity> update(@PathVariable Long id, @RequestBody NotificationTemplateEntity request) {
        return Result.ok(templateService.update(id, request));
    }

    @Operation(summary = "渲染预览（按编码 + 变量试渲染标题/正文）")
    @PostMapping("/preview")
    public Result<Map<String, String>> preview(@RequestBody PreviewRequest request) {
        NotificationTemplateEntity template = templateService.findActive(request.templateCode());
        if (template == null) {
            throw new BizException(ErrorCode.TEMPLATE_NOT_FOUND, "模板不存在或已停用: " + request.templateCode());
        }
        return Result.ok(Map.of(
                "title", templateService.render(template.getTitleTemplate(), request.vars()),
                "content", templateService.render(template.getContentTemplate(), request.vars())));
    }

    public record PreviewRequest(String templateCode, Map<String, Object> vars) {
    }
}

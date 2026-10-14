package com.demandhub.notification.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationTemplateEntity;
import com.demandhub.notification.mapper.NotificationTemplateMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 通知模板（M8 FR-M8-03）：CRUD + 变量渲染引擎。
 * 占位符格式 ${var}，未提供的变量渲染为空串（避免把占位符直接发给用户）。
 */
@Service
public class TemplateService {

    private static final Pattern VARIABLE = Pattern.compile("\\$\\{([a-zA-Z0-9_]+)}");

    private final NotificationTemplateMapper templateMapper;

    public TemplateService(NotificationTemplateMapper templateMapper) {
        this.templateMapper = templateMapper;
    }

    public List<NotificationTemplateEntity> list() {
        return templateMapper.selectList(new LambdaQueryWrapper<NotificationTemplateEntity>()
                .orderByAsc(NotificationTemplateEntity::getId));
    }

    public NotificationTemplateEntity requireById(Long id) {
        NotificationTemplateEntity entity = templateMapper.selectById(id);
        if (entity == null) {
            throw new BizException(ErrorCode.TEMPLATE_NOT_FOUND);
        }
        return entity;
    }

    /** 按编码查启用模板；不存在返回 null（事件缺模板时跳过发送而不是报错） */
    public NotificationTemplateEntity findActive(String templateCode) {
        return templateMapper.selectOne(new LambdaQueryWrapper<NotificationTemplateEntity>()
                .eq(NotificationTemplateEntity::getTemplateCode, templateCode)
                .eq(NotificationTemplateEntity::getStatus, "ACTIVE"));
    }

    public NotificationTemplateEntity create(NotificationTemplateEntity request) {
        validate(request);
        if (Boolean.TRUE.equals(templateMapper.exists(new LambdaQueryWrapper<NotificationTemplateEntity>()
                .eq(NotificationTemplateEntity::getTemplateCode, request.getTemplateCode())))) {
            throw new BizException(ErrorCode.BIZ_ERROR, "模板编码已存在: " + request.getTemplateCode());
        }
        request.setId(null);
        if (!StringUtils.hasText(request.getStatus())) {
            request.setStatus("ACTIVE");
        }
        templateMapper.insert(request);
        return request;
    }

    public NotificationTemplateEntity update(Long id, NotificationTemplateEntity request) {
        NotificationTemplateEntity entity = requireById(id);
        // 模板编码不可改（事件按编码关联）
        if (StringUtils.hasText(request.getTemplateName())) {
            entity.setTemplateName(request.getTemplateName());
        }
        if (StringUtils.hasText(request.getTitleTemplate())) {
            entity.setTitleTemplate(request.getTitleTemplate());
        }
        if (StringUtils.hasText(request.getContentTemplate())) {
            entity.setContentTemplate(request.getContentTemplate());
        }
        if (StringUtils.hasText(request.getStatus())) {
            entity.setStatus(request.getStatus());
        }
        if (request.getRemark() != null) {
            entity.setRemark(request.getRemark());
        }
        templateMapper.updateById(entity);
        return entity;
    }

    /** 渲染：${var} → vars 中的值，未提供的变量替换为空串 */
    public String render(String template, Map<String, Object> vars) {
        if (template == null) {
            return null;
        }
        Matcher matcher = VARIABLE.matcher(template);
        StringBuilder sb = new StringBuilder();
        while (matcher.find()) {
            Object value = vars == null ? null : vars.get(matcher.group(1));
            matcher.appendReplacement(sb, Matcher.quoteReplacement(value == null ? "" : String.valueOf(value)));
        }
        matcher.appendTail(sb);
        return sb.toString();
    }

    private void validate(NotificationTemplateEntity request) {
        if (!StringUtils.hasText(request.getTemplateCode()) || !StringUtils.hasText(request.getTemplateName())
                || !StringUtils.hasText(request.getTitleTemplate()) || !StringUtils.hasText(request.getContentTemplate())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "模板编码/名称/标题/正文不能为空");
        }
    }
}

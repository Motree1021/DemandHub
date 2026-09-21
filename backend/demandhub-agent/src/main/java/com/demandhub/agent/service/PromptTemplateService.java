package com.demandhub.agent.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.agent.entity.AgentPromptTemplateEntity;
import com.demandhub.agent.mapper.AgentPromptTemplateMapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Prompt 模板（FR-M9：模板可配置，一期存 agent_prompt_template 表，二期可迁 Nacos）。
 * 渲染规则与通知模板一致：${var} 占位替换。
 */
@Service
public class PromptTemplateService {

    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(\\w+)}");

    private final AgentPromptTemplateMapper templateMapper;

    public PromptTemplateService(AgentPromptTemplateMapper templateMapper) {
        this.templateMapper = templateMapper;
    }

    /** 取启用模板并渲染变量；模板缺失时返回空串（Mock 场景不阻断，真实 LLM 场景应告警） */
    public String render(String templateCode, Map<String, Object> vars) {
        AgentPromptTemplateEntity template = templateMapper.selectOne(new LambdaQueryWrapper<AgentPromptTemplateEntity>()
                .eq(AgentPromptTemplateEntity::getTemplateCode, templateCode)
                .eq(AgentPromptTemplateEntity::getStatus, "ACTIVE")
                .last("LIMIT 1"));
        if (template == null) {
            return "";
        }
        String content = template.getContent();
        if (vars == null || vars.isEmpty()) {
            return content;
        }
        Matcher matcher = PLACEHOLDER.matcher(content);
        StringBuilder sb = new StringBuilder();
        while (matcher.find()) {
            Object value = vars.get(matcher.group(1));
            matcher.appendReplacement(sb, Matcher.quoteReplacement(value == null ? "" : String.valueOf(value)));
        }
        matcher.appendTail(sb);
        return sb.toString();
    }

    public List<AgentPromptTemplateEntity> listAll() {
        return templateMapper.selectList(new LambdaQueryWrapper<AgentPromptTemplateEntity>()
                .orderByAsc(AgentPromptTemplateEntity::getId));
    }

    /** 管理端更新（内容/状态/备注），即时生效无需重启 */
    public AgentPromptTemplateEntity update(Long id, String content, String status, String remark) {
        AgentPromptTemplateEntity template = templateMapper.selectById(id);
        if (template == null) {
            throw new BizException(ErrorCode.PROMPT_TEMPLATE_NOT_FOUND);
        }
        if (StringUtils.hasText(content)) {
            template.setContent(content);
        }
        if (StringUtils.hasText(status)) {
            if (!"ACTIVE".equals(status) && !"DISABLED".equals(status)) {
                throw new BizException(ErrorCode.PARAM_INVALID, "状态仅支持 ACTIVE/DISABLED");
            }
            template.setStatus(status);
        }
        if (remark != null) {
            template.setRemark(remark);
        }
        templateMapper.updateById(template);
        return template;
    }
}

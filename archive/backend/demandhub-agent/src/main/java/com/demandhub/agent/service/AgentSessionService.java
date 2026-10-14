package com.demandhub.agent.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.agent.entity.AgentMessageEntity;
import com.demandhub.agent.entity.AgentSessionEntity;
import com.demandhub.agent.mapper.AgentMessageMapper;
import com.demandhub.agent.mapper.AgentSessionMapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

/**
 * Agent 会话管理（FR-M9-01/02：agent_session / agent_message CRUD）。
 * 会话仅归属人可见。
 */
@Service
public class AgentSessionService {

    private final AgentSessionMapper sessionMapper;
    private final AgentMessageMapper messageMapper;

    public AgentSessionService(AgentSessionMapper sessionMapper, AgentMessageMapper messageMapper) {
        this.sessionMapper = sessionMapper;
        this.messageMapper = messageMapper;
    }

    /** 新建会话（scene：SUBMIT_GUIDE 提报启发 / HANDLE_ASSIST 处理辅助） */
    public AgentSessionEntity create(String scene, Long demandId, String firstMessage) {
        CurrentUser user = requireLogin();
        if (!"SUBMIT_GUIDE".equals(scene) && !"HANDLE_ASSIST".equals(scene)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "scene 仅支持 SUBMIT_GUIDE/HANDLE_ASSIST");
        }
        AgentSessionEntity session = new AgentSessionEntity();
        session.setSessionNo(UUID.randomUUID().toString().replace("-", ""));
        session.setUserId(user.getId());
        session.setScene(scene);
        session.setDemandId(demandId);
        session.setTitle(firstMessage == null ? "新会话"
                : firstMessage.substring(0, Math.min(firstMessage.length(), 40)));
        session.setStatus("ACTIVE");
        sessionMapper.insert(session);
        return session;
    }

    /** 我的会话列表（按场景筛选，倒序） */
    public List<AgentSessionEntity> listMine(String scene) {
        CurrentUser user = requireLogin();
        return sessionMapper.selectList(new LambdaQueryWrapper<AgentSessionEntity>()
                .eq(AgentSessionEntity::getUserId, user.getId())
                .eq(scene != null && !scene.isBlank(), AgentSessionEntity::getScene, scene)
                .orderByDesc(AgentSessionEntity::getId)
                .last("LIMIT 50"));
    }

    /** 会话历史消息（仅归属人可见，按时间升序） */
    public List<AgentMessageEntity> messages(Long sessionId) {
        requireOwned(sessionId);
        return messageMapper.selectList(new LambdaQueryWrapper<AgentMessageEntity>()
                .eq(AgentMessageEntity::getSessionId, sessionId)
                .orderByAsc(AgentMessageEntity::getId));
    }

    /** 关闭会话 */
    public void close(Long sessionId) {
        AgentSessionEntity session = requireOwned(sessionId);
        session.setStatus("CLOSED");
        sessionMapper.updateById(session);
    }

    /** 校验会话归属并返回（不存在或非本人 → 404/403） */
    public AgentSessionEntity requireOwned(Long sessionId) {
        CurrentUser user = requireLogin();
        AgentSessionEntity session = sessionMapper.selectById(sessionId);
        if (session == null) {
            throw new BizException(ErrorCode.AGENT_SESSION_NOT_FOUND);
        }
        if (!user.getId().equals(session.getUserId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅会话创建人可操作");
        }
        return session;
    }

    /** 追加消息（content 必填；structuredPayload 可选 JSON） */
    public AgentMessageEntity appendMessage(Long sessionId, String role, String content, String structuredPayload) {
        AgentMessageEntity message = new AgentMessageEntity();
        message.setSessionId(sessionId);
        message.setRole(role);
        message.setContent(content == null ? "" : content);
        message.setStructuredPayload(structuredPayload);
        messageMapper.insert(message);
        return message;
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}

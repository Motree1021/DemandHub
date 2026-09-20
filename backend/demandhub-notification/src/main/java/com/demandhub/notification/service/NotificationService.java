package com.demandhub.notification.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationEntity;
import com.demandhub.notification.entity.NotificationTemplateEntity;
import com.demandhub.notification.mapper.NotificationMapper;
import com.demandhub.notification.mq.WecomPushProducer;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Map;

/**
 * 站内信（FR-M7-01）：通知写入（事件消费侧）、我的通知列表、未读计数、标记已读。
 * 每个接收人写两行：IN_APP（写入即送达）+ WECOM（PENDING，MQ 异步推送）。
 */
@Slf4j
@Service
public class NotificationService {

    private final NotificationMapper notificationMapper;
    private final TemplateService templateService;
    private final PreferenceService preferenceService;
    private final WecomPushProducer wecomPushProducer;

    /** 通知跳转链接前缀（需求详情页路由，阶段 5 前端对齐） */
    @Value("${demandhub.notification.link-prefix:/demand/detail/}")
    private String linkPrefix;

    public NotificationService(NotificationMapper notificationMapper, TemplateService templateService,
                               PreferenceService preferenceService, WecomPushProducer wecomPushProducer) {
        this.notificationMapper = notificationMapper;
        this.templateService = templateService;
        this.preferenceService = preferenceService;
        this.wecomPushProducer = wecomPushProducer;
    }

    /**
     * 通知写入入口（事件消费侧调用）：渲染模板 → 偏好过滤 → 落库 → 投递企微推送任务。
     *
     * @return 实际发送的接收人数（过滤后）
     */
    public int sendToReceivers(Long demandId, String templateCode, String notifyType,
                               Collection<Long> receiverIds, Map<String, Object> vars) {
        if (receiverIds == null || receiverIds.isEmpty()) {
            return 0;
        }
        NotificationTemplateEntity template = templateService.findActive(templateCode);
        if (template == null) {
            log.warn("[Notification] 模板缺失或停用，跳过发送: {}", templateCode);
            return 0;
        }
        String title = templateService.render(template.getTitleTemplate(), vars);
        String content = templateService.render(template.getContentTemplate(), vars);
        String link = demandId == null ? null : linkPrefix + demandId;
        LocalDateTime now = LocalDateTime.now();
        int sent = 0;
        for (Long receiverId : receiverIds) {
            if (receiverId == null || !preferenceService.isEnabled(receiverId, notifyType)) {
                continue;
            }
            NotificationEntity inApp = buildRow(demandId, receiverId, "IN_APP", templateCode, title, content, link);
            inApp.setSendStatus("SENT");
            inApp.setSentAt(now);
            notificationMapper.insert(inApp);

            NotificationEntity wecom = buildRow(demandId, receiverId, "WECOM", templateCode, title, content, link);
            notificationMapper.insert(wecom);
            wecomPushProducer.send(wecom.getId());
            sent++;
        }
        return sent;
    }

    /** 我的通知列表（站内信渠道，分页 + 未读/已读筛选） */
    public Page<NotificationEntity> listMine(Long userId, Boolean isRead, long current, long size) {
        LambdaQueryWrapper<NotificationEntity> wrapper = new LambdaQueryWrapper<NotificationEntity>()
                .eq(NotificationEntity::getReceiverId, userId)
                .eq(NotificationEntity::getChannel, "IN_APP")
                .orderByDesc(NotificationEntity::getId);
        if (isRead != null) {
            wrapper.eq(NotificationEntity::getIsRead, isRead ? 1 : 0);
        }
        return notificationMapper.selectPage(new Page<>(current, size), wrapper);
    }

    /** 未读计数（实时：直接查库） */
    public long unreadCount(Long userId) {
        return notificationMapper.selectCount(new LambdaQueryWrapper<NotificationEntity>()
                .eq(NotificationEntity::getReceiverId, userId)
                .eq(NotificationEntity::getChannel, "IN_APP")
                .eq(NotificationEntity::getIsRead, 0));
    }

    /** 标记已读（仅本人的站内信） */
    public void markRead(Long id, Long userId) {
        NotificationEntity entity = notificationMapper.selectById(id);
        if (entity == null || !"IN_APP".equals(entity.getChannel()) || !userId.equals(entity.getReceiverId())) {
            throw new BizException(ErrorCode.NOTIFICATION_NOT_FOUND);
        }
        if (entity.getIsRead() != null && entity.getIsRead() == 1) {
            return;
        }
        notificationMapper.update(null, new LambdaUpdateWrapper<NotificationEntity>()
                .eq(NotificationEntity::getId, id)
                .set(NotificationEntity::getIsRead, 1)
                .set(NotificationEntity::getReadAt, LocalDateTime.now()));
    }

    /** 全部已读 */
    public int markAllRead(Long userId) {
        return notificationMapper.update(null, new LambdaUpdateWrapper<NotificationEntity>()
                .eq(NotificationEntity::getReceiverId, userId)
                .eq(NotificationEntity::getChannel, "IN_APP")
                .eq(NotificationEntity::getIsRead, 0)
                .set(NotificationEntity::getIsRead, 1)
                .set(NotificationEntity::getReadAt, LocalDateTime.now()));
    }

    private NotificationEntity buildRow(Long demandId, Long receiverId, String channel, String templateCode,
                                        String title, String content, String link) {
        NotificationEntity entity = new NotificationEntity();
        entity.setDemandId(demandId);
        entity.setReceiverId(receiverId);
        entity.setChannel(channel);
        entity.setTemplateCode(templateCode);
        entity.setTitle(title);
        entity.setContent(content);
        entity.setLink(link);
        entity.setIsRead(0);
        entity.setSendStatus("PENDING");
        entity.setRetryCount(0);
        return entity;
    }
}

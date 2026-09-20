package com.demandhub.notification.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.entity.NotificationPreferenceEntity;
import com.demandhub.notification.mapper.NotificationPreferenceMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;

/**
 * 通知偏好（FR-M7-03）：用户可关闭非关键通知类型，发送前过滤；待办提醒 TODO 不可关闭。
 * 无记录 = 默认开启。读侧 Redis 缓存 60s，变更时主动失效（偏好即时生效）。
 */
@Service
public class PreferenceService {

    private static final Duration CACHE_TTL = Duration.ofSeconds(60);
    private static final String CACHE_KEY_PREFIX = "notify:pref:";

    private final NotificationPreferenceMapper preferenceMapper;
    private final StringRedisTemplate redis;

    public PreferenceService(NotificationPreferenceMapper preferenceMapper, StringRedisTemplate redis) {
        this.preferenceMapper = preferenceMapper;
        this.redis = redis;
    }

    /** 发送前过滤：该用户是否接收此类通知（TODO 恒 true） */
    public boolean isEnabled(Long userId, String notifyType) {
        if (userId == null || !NotifyTypes.isClosable(notifyType)) {
            return true;
        }
        String cacheKey = CACHE_KEY_PREFIX + userId + ":" + notifyType;
        String cached = redis.opsForValue().get(cacheKey);
        if (cached != null) {
            return "1".equals(cached);
        }
        NotificationPreferenceEntity pref = preferenceMapper.selectOne(new LambdaQueryWrapper<NotificationPreferenceEntity>()
                .eq(NotificationPreferenceEntity::getUserId, userId)
                .eq(NotificationPreferenceEntity::getNotifyType, notifyType));
        boolean enabled = pref == null || pref.getEnabled() == null || pref.getEnabled() == 1;
        redis.opsForValue().set(cacheKey, enabled ? "1" : "0", CACHE_TTL);
        return enabled;
    }

    public List<NotificationPreferenceEntity> listMine(Long userId) {
        return preferenceMapper.selectList(new LambdaQueryWrapper<NotificationPreferenceEntity>()
                .eq(NotificationPreferenceEntity::getUserId, userId));
    }

    /** 设置某类通知开关（upsert）；TODO 拒绝关闭 */
    public void setEnabled(Long userId, String notifyType, boolean enabled) {
        if (!NotifyTypes.ALL.contains(notifyType)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "非法通知类型: " + notifyType);
        }
        if (!NotifyTypes.isClosable(notifyType) && !enabled) {
            throw new BizException(ErrorCode.PARAM_INVALID, "待办提醒为关键通知，不可关闭");
        }
        NotificationPreferenceEntity pref = preferenceMapper.selectOne(new LambdaQueryWrapper<NotificationPreferenceEntity>()
                .eq(NotificationPreferenceEntity::getUserId, userId)
                .eq(NotificationPreferenceEntity::getNotifyType, notifyType));
        if (pref == null) {
            pref = new NotificationPreferenceEntity();
            pref.setUserId(userId);
            pref.setNotifyType(notifyType);
            pref.setEnabled(enabled ? 1 : 0);
            preferenceMapper.insert(pref);
        } else {
            pref.setEnabled(enabled ? 1 : 0);
            preferenceMapper.updateById(pref);
        }
        redis.delete(CACHE_KEY_PREFIX + userId + ":" + notifyType);
    }
}

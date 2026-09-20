package com.demandhub.demand.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

/**
 * 需求编号生成器（FR-M2-06）：{TYPE}-{YYYYMMDD}-{NNN}，按类型按日流水。
 * Redis INCR 原子递增保证并发不重复；全部提交成功时序号连续不跳号；
 * DB uk_demand_no 唯一索引兜底。
 */
@Service
public class DemandNoGenerator {

    private static final String KEY_PREFIX = "demand:no:";
    private static final Duration KEY_TTL = Duration.ofHours(48);

    private final StringRedisTemplate redis;

    public DemandNoGenerator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String next(String typeCode) {
        String day = LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE);
        String key = KEY_PREFIX + typeCode + ":" + day;
        Long seq = redis.opsForValue().increment(key);
        if (seq == null) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "需求编号生成失败");
        }
        if (seq == 1L) {
            redis.expire(key, KEY_TTL);
        }
        return String.format("%s-%s-%03d", typeCode, day, seq);
    }
}

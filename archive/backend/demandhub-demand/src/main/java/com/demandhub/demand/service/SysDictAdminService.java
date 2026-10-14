package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.SysDictEntity;
import com.demandhub.demand.mapper.SysDictMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.util.List;
import java.util.stream.Collectors;

/**
 * M8 通用字典管理（FR-M8-04）：sys_dict 按 dict_type 分组维护。
 * 字典项停用后历史数据仍展示原名称（历史存编码，展示走名称快照/字典联查）。
 * 下拉项（listActive）缓存 Redis 60 秒，管理端增删改即时失效。
 */
@Service
public class SysDictAdminService {

    private static final String CACHE_PREFIX = "dict:active:";
    private static final Duration CACHE_TTL = Duration.ofSeconds(60);

    private final SysDictMapper sysDictMapper;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SysDictAdminService(SysDictMapper sysDictMapper, StringRedisTemplate redis) {
        this.sysDictMapper = sysDictMapper;
        this.redis = redis;
    }

    public List<SysDictEntity> list(String dictType) {
        LambdaQueryWrapper<SysDictEntity> wrapper = new LambdaQueryWrapper<SysDictEntity>()
                .orderByAsc(SysDictEntity::getDictType).orderByAsc(SysDictEntity::getSort).orderByAsc(SysDictEntity::getId);
        if (StringUtils.hasText(dictType)) {
            wrapper.eq(SysDictEntity::getDictType, dictType);
        }
        return sysDictMapper.selectList(wrapper);
    }

    /** 下拉项查询（登录用户可用）：仅启用项；Redis 60s 缓存，管理端变更即时失效 */
    public List<SysDictEntity> listActive(String dictType) {
        String key = CACHE_PREFIX + dictType;
        try {
            String json = redis.opsForValue().get(key);
            if (json != null) {
                return objectMapper.readValue(json,
                        objectMapper.getTypeFactory().constructCollectionType(List.class, SysDictEntity.class));
            }
        } catch (Exception ignored) {
            // 缓存异常回源 DB
        }
        List<SysDictEntity> list = sysDictMapper.selectList(new LambdaQueryWrapper<SysDictEntity>()
                .eq(SysDictEntity::getDictType, dictType)
                .eq(SysDictEntity::getStatus, "ACTIVE")
                .orderByAsc(SysDictEntity::getSort).orderByAsc(SysDictEntity::getId));
        try {
            redis.opsForValue().set(key, objectMapper.writeValueAsString(list), CACHE_TTL);
        } catch (Exception ignored) {
            // 缓存失败不影响主流程
        }
        return list;
    }

    /** 管理端变更后失效该分组缓存 */
    private void evictCache(String dictType) {
        try {
            if (dictType != null) {
                redis.delete(CACHE_PREFIX + dictType);
            }
        } catch (Exception ignored) {
            // 失效失败靠 TTL 兜底
        }
    }

    public List<String> listTypes() {
        return sysDictMapper.selectList(null).stream()
                .map(SysDictEntity::getDictType).distinct().sorted().collect(Collectors.toList());
    }

    public SysDictEntity requireById(Long id) {
        SysDictEntity entity = sysDictMapper.selectById(id);
        if (entity == null) {
            throw new BizException(ErrorCode.DICT_ITEM_NOT_FOUND);
        }
        return entity;
    }

    public SysDictEntity create(SysDictEntity request) {
        if (!StringUtils.hasText(request.getDictType()) || !StringUtils.hasText(request.getItemCode())
                || !StringUtils.hasText(request.getItemName())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "字典分组/编码/名称不能为空");
        }
        if (Boolean.TRUE.equals(sysDictMapper.exists(new LambdaQueryWrapper<SysDictEntity>()
                .eq(SysDictEntity::getDictType, request.getDictType())
                .eq(SysDictEntity::getItemCode, request.getItemCode())))) {
            throw new BizException(ErrorCode.BIZ_ERROR,
                    "字典项已存在: " + request.getDictType() + "/" + request.getItemCode());
        }
        request.setId(null);
        if (!StringUtils.hasText(request.getStatus())) {
            request.setStatus("ACTIVE");
        }
        if (request.getSort() == null) {
            request.setSort(0);
        }
        sysDictMapper.insert(request);
        evictCache(request.getDictType());
        return request;
    }

    public SysDictEntity update(Long id, SysDictEntity request) {
        SysDictEntity entity = requireById(id);
        // dict_type / item_code 不可改（历史数据按编码关联）
        if (StringUtils.hasText(request.getItemName())) {
            entity.setItemName(request.getItemName());
        }
        if (request.getSort() != null) {
            entity.setSort(request.getSort());
        }
        if (StringUtils.hasText(request.getStatus())) {
            entity.setStatus(request.getStatus());
        }
        sysDictMapper.updateById(entity);
        evictCache(entity.getDictType());
        return entity;
    }
}

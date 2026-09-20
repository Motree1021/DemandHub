package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.SysDictEntity;
import com.demandhub.demand.mapper.SysDictMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

/**
 * M8 通用字典管理（FR-M8-04）：sys_dict 按 dict_type 分组维护。
 * 字典项停用后历史数据仍展示原名称（历史存编码，展示走名称快照/字典联查）。
 */
@Service
public class SysDictAdminService {

    private final SysDictMapper sysDictMapper;

    public SysDictAdminService(SysDictMapper sysDictMapper) {
        this.sysDictMapper = sysDictMapper;
    }

    public List<SysDictEntity> list(String dictType) {
        LambdaQueryWrapper<SysDictEntity> wrapper = new LambdaQueryWrapper<SysDictEntity>()
                .orderByAsc(SysDictEntity::getDictType).orderByAsc(SysDictEntity::getSort).orderByAsc(SysDictEntity::getId);
        if (StringUtils.hasText(dictType)) {
            wrapper.eq(SysDictEntity::getDictType, dictType);
        }
        return sysDictMapper.selectList(wrapper);
    }

    /** 下拉项查询（登录用户可用）：仅启用项 */
    public List<SysDictEntity> listActive(String dictType) {
        return sysDictMapper.selectList(new LambdaQueryWrapper<SysDictEntity>()
                .eq(SysDictEntity::getDictType, dictType)
                .eq(SysDictEntity::getStatus, "ACTIVE")
                .orderByAsc(SysDictEntity::getSort).orderByAsc(SysDictEntity::getId));
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
        return entity;
    }
}

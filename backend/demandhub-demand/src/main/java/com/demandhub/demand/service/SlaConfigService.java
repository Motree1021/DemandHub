package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.SlaConfigEntity;
import com.demandhub.demand.mapper.SlaConfigMapper;
import com.demandhub.demand.statemachine.DemandStatus;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

/**
 * M8 SLA 配置管理：按 类型 × 状态 配置最长停留时长（黄色预警 / 红色告警阈值，单位分钟）。
 */
@Service
public class SlaConfigService {

    private final SlaConfigMapper slaConfigMapper;

    public SlaConfigService(SlaConfigMapper slaConfigMapper) {
        this.slaConfigMapper = slaConfigMapper;
    }

    public List<SlaConfigEntity> list(String demandTypeCode) {
        LambdaQueryWrapper<SlaConfigEntity> wrapper = new LambdaQueryWrapper<SlaConfigEntity>()
                .orderByAsc(SlaConfigEntity::getDemandTypeCode).orderByAsc(SlaConfigEntity::getId);
        if (StringUtils.hasText(demandTypeCode)) {
            wrapper.eq(SlaConfigEntity::getDemandTypeCode, demandTypeCode);
        }
        return slaConfigMapper.selectList(wrapper);
    }

    public SlaConfigEntity requireById(Long id) {
        SlaConfigEntity entity = slaConfigMapper.selectById(id);
        if (entity == null) {
            throw new BizException(ErrorCode.SLA_CONFIG_NOT_FOUND);
        }
        return entity;
    }

    public SlaConfigEntity create(SlaConfigEntity request) {
        validate(request);
        ensureUnique(request.getDemandTypeCode(), request.getStatus(), null);
        request.setId(null);
        if (request.getEnabled() == null) {
            request.setEnabled(1);
        }
        slaConfigMapper.insert(request);
        return request;
    }

    public SlaConfigEntity update(Long id, SlaConfigEntity request) {
        SlaConfigEntity entity = requireById(id);
        String typeCode = StringUtils.hasText(request.getDemandTypeCode()) ? request.getDemandTypeCode() : entity.getDemandTypeCode();
        String status = StringUtils.hasText(request.getStatus()) ? request.getStatus() : entity.getStatus();
        Integer warn = request.getWarnMinutes() != null ? request.getWarnMinutes() : entity.getWarnMinutes();
        Integer max = request.getMaxMinutes() != null ? request.getMaxMinutes() : entity.getMaxMinutes();
        SlaConfigEntity merged = new SlaConfigEntity();
        merged.setDemandTypeCode(typeCode);
        merged.setStatus(status);
        merged.setWarnMinutes(warn);
        merged.setMaxMinutes(max);
        validate(merged);
        ensureUnique(typeCode, status, id);
        entity.setDemandTypeCode(typeCode);
        entity.setStatus(status);
        entity.setWarnMinutes(warn);
        entity.setMaxMinutes(max);
        if (request.getEnabled() != null) {
            entity.setEnabled(request.getEnabled());
        }
        if (request.getRemark() != null) {
            entity.setRemark(request.getRemark());
        }
        slaConfigMapper.updateById(entity);
        return entity;
    }

    public void delete(Long id) {
        requireById(id);
        slaConfigMapper.deleteById(id);
    }

    private void validate(SlaConfigEntity request) {
        if (!StringUtils.hasText(request.getDemandTypeCode()) || !StringUtils.hasText(request.getStatus())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "需求类型与状态不能为空");
        }
        try {
            DemandStatus.valueOf(request.getStatus());
        } catch (IllegalArgumentException e) {
            throw new BizException(ErrorCode.PARAM_INVALID, "非法状态: " + request.getStatus());
        }
        if (request.getWarnMinutes() == null || request.getMaxMinutes() == null
                || request.getWarnMinutes() < 1 || request.getMaxMinutes() < 1) {
            throw new BizException(ErrorCode.PARAM_INVALID, "预警/告警阈值须为正整数（分钟）");
        }
        if (request.getWarnMinutes() >= request.getMaxMinutes()) {
            throw new BizException(ErrorCode.PARAM_INVALID, "黄色预警阈值须小于红色告警阈值");
        }
    }

    private void ensureUnique(String typeCode, String status, Long excludeId) {
        LambdaQueryWrapper<SlaConfigEntity> wrapper = new LambdaQueryWrapper<SlaConfigEntity>()
                .eq(SlaConfigEntity::getDemandTypeCode, typeCode)
                .eq(SlaConfigEntity::getStatus, status);
        if (excludeId != null) {
            wrapper.ne(SlaConfigEntity::getId, excludeId);
        }
        if (Boolean.TRUE.equals(slaConfigMapper.exists(wrapper))) {
            throw new BizException(ErrorCode.BIZ_ERROR, "该类型 × 状态的 SLA 配置已存在: " + typeCode + "/" + status);
        }
    }
}

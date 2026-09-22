package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.statemachine.StateMachineConfig;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

/**
 * M8 需求类型字典管理（FR-M8-01）：基于已有 demand_type 表，不重建。
 * 类型编码创建后不可改（历史数据按编码关联）；停用不影响旧数据展示。
 */
@Service
public class DemandTypeAdminService {

    private final DemandTypeMapper demandTypeMapper;
    private final OrgSnapshotViewMapper orgSnapshotMapper;

    public DemandTypeAdminService(DemandTypeMapper demandTypeMapper, OrgSnapshotViewMapper orgSnapshotMapper) {
        this.demandTypeMapper = demandTypeMapper;
        this.orgSnapshotMapper = orgSnapshotMapper;
    }

    public List<DemandTypeEntity> list() {
        return demandTypeMapper.selectList(new LambdaQueryWrapper<DemandTypeEntity>()
                .orderByAsc(DemandTypeEntity::getSort).orderByAsc(DemandTypeEntity::getId));
    }

    public DemandTypeEntity requireById(Long id) {
        DemandTypeEntity entity = demandTypeMapper.selectById(id);
        if (entity == null) {
            throw new BizException(ErrorCode.DEMAND_TYPE_NOT_FOUND);
        }
        return entity;
    }

    public DemandTypeEntity create(DemandTypeEntity request) {
        if (!StringUtils.hasText(request.getTypeCode()) || !StringUtils.hasText(request.getTypeName())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "类型编码与名称不能为空");
        }
        String typeCode = request.getTypeCode().trim().toUpperCase();
        if (!typeCode.matches("[A-Z0-9_]{2,16}")) {
            throw new BizException(ErrorCode.PARAM_INVALID, "类型编码须为 2~16 位大写字母/数字/下划线");
        }
        if (Boolean.TRUE.equals(demandTypeMapper.exists(new LambdaQueryWrapper<DemandTypeEntity>()
                .eq(DemandTypeEntity::getTypeCode, typeCode)))) {
            throw new BizException(ErrorCode.BIZ_ERROR, "类型编码已存在: " + typeCode);
        }
        validateRefs(request.getDefaultOrgId(), request.getStateMachineKey());
        request.setId(null);
        request.setTypeCode(typeCode);
        if (!StringUtils.hasText(request.getStateMachineKey())) {
            request.setStateMachineKey(StateMachineConfig.DEFAULT_KEY);
        }
        if (!StringUtils.hasText(request.getStatus())) {
            request.setStatus("ACTIVE");
        }
        if (request.getSort() == null) {
            request.setSort(0);
        }
        demandTypeMapper.insert(request);
        return request;
    }

    public DemandTypeEntity update(Long id, DemandTypeEntity request) {
        DemandTypeEntity entity = requireById(id);
        // 类型编码不可改（历史需求按编码关联）
        if (StringUtils.hasText(request.getTypeName())) {
            entity.setTypeName(request.getTypeName());
        }
        if (request.getParentTypeCode() != null) {
            entity.setParentTypeCode(StringUtils.hasText(request.getParentTypeCode()) ? request.getParentTypeCode() : null);
        }
        if (request.getDefaultOrgId() != null) {
            validateRefs(request.getDefaultOrgId(), null);
            entity.setDefaultOrgId(request.getDefaultOrgId());
        }
        if (StringUtils.hasText(request.getStateMachineKey())) {
            validateRefs(null, request.getStateMachineKey());
            entity.setStateMachineKey(request.getStateMachineKey());
        }
        if (request.getSort() != null) {
            entity.setSort(request.getSort());
        }
        if (StringUtils.hasText(request.getStatus())) {
            entity.setStatus(request.getStatus());
        }
        demandTypeMapper.updateById(entity);
        return entity;
    }

    private void validateRefs(Long defaultOrgId, String stateMachineKey) {
        if (defaultOrgId != null) {
            OrgSnapshotView org = orgSnapshotMapper.selectOne(new LambdaQueryWrapper<OrgSnapshotView>()
                    .eq(OrgSnapshotView::getId, defaultOrgId));
            if (org == null) {
                throw new BizException(ErrorCode.PARAM_INVALID, "默认承接组织不存在: " + defaultOrgId);
            }
        }
        if (StringUtils.hasText(stateMachineKey) && stateMachineKey.length() > 64) {
            throw new BizException(ErrorCode.PARAM_INVALID, "状态机标识过长");
        }
    }
}

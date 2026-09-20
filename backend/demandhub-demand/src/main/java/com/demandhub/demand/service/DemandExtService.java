package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandExtMaterialEntity;
import com.demandhub.demand.entity.DemandExtTechEntity;
import com.demandhub.demand.entity.DemandExtTrainingEntity;
import com.demandhub.demand.mapper.DemandExtMaterialMapper;
import com.demandhub.demand.mapper.DemandExtTechMapper;
import com.demandhub.demand.mapper.DemandExtTrainingMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

/**
 * 三类需求扩展表读写（TECH/MATL/TRAIN，1:1）。
 * 提交时整行写入；补充重提时仅更新提供的字段。
 */
@Service
public class DemandExtService {

    private final DemandExtTechMapper techMapper;
    private final DemandExtMaterialMapper materialMapper;
    private final DemandExtTrainingMapper trainingMapper;

    public DemandExtService(DemandExtTechMapper techMapper,
                            DemandExtMaterialMapper materialMapper,
                            DemandExtTrainingMapper trainingMapper) {
        this.techMapper = techMapper;
        this.materialMapper = materialMapper;
        this.trainingMapper = trainingMapper;
    }

    public void writeExt(Long demandId, String typeCode, Map<String, Object> ext) {
        if (ext == null) {
            ext = Map.of();
        }
        switch (typeCode) {
            case "TECH" -> {
                DemandExtTechEntity e = new DemandExtTechEntity();
                e.setDemandId(demandId);
                e.setRelatedSystem(asString(ext.get("relatedSystem")));
                e.setRelatedModule(asString(ext.get("relatedModule")));
                e.setBusinessScenario(asString(ext.get("businessScenario")));
                e.setAcceptanceCriteria(asString(ext.get("acceptanceCriteria")));
                techMapper.insert(e);
            }
            case "MATL" -> {
                DemandExtMaterialEntity e = new DemandExtMaterialEntity();
                e.setDemandId(demandId);
                e.setMaterialSubtype(asString(ext.get("materialSubtype")));
                e.setUsageScenario(asString(ext.get("usageScenario")));
                e.setQuantity(asInteger(ext.get("quantity")));
                e.setExpectedArrivalAt(asDateTime(ext.get("expectedArrivalAt")));
                materialMapper.insert(e);
            }
            case "TRAIN" -> {
                DemandExtTrainingEntity e = new DemandExtTrainingEntity();
                e.setDemandId(demandId);
                e.setTrainingSubtype(asString(ext.get("trainingSubtype")));
                e.setTraineeObject(asString(ext.get("traineeObject")));
                e.setTraineeCount(asInteger(ext.get("traineeCount")));
                e.setExpectedCompleteAt(asDateTime(ext.get("expectedCompleteAt")));
                trainingMapper.insert(e);
            }
            default -> throw new BizException(ErrorCode.DEMAND_TYPE_INVALID, "不支持的需求类型: " + typeCode);
        }
    }

    /** 补充重提时部分更新（仅更新 map 中提供的 key） */
    public void patchExt(Long demandId, String typeCode, Map<String, Object> ext) {
        if (ext == null || ext.isEmpty()) {
            return;
        }
        switch (typeCode) {
            case "TECH" -> {
                DemandExtTechEntity e = techMapper.selectOne(new LambdaQueryWrapper<DemandExtTechEntity>()
                        .eq(DemandExtTechEntity::getDemandId, demandId));
                if (e == null) {
                    writeExt(demandId, typeCode, ext);
                    return;
                }
                if (ext.containsKey("relatedSystem")) e.setRelatedSystem(asString(ext.get("relatedSystem")));
                if (ext.containsKey("relatedModule")) e.setRelatedModule(asString(ext.get("relatedModule")));
                if (ext.containsKey("businessScenario")) e.setBusinessScenario(asString(ext.get("businessScenario")));
                if (ext.containsKey("acceptanceCriteria")) e.setAcceptanceCriteria(asString(ext.get("acceptanceCriteria")));
                techMapper.updateById(e);
            }
            case "MATL" -> {
                DemandExtMaterialEntity e = materialMapper.selectOne(new LambdaQueryWrapper<DemandExtMaterialEntity>()
                        .eq(DemandExtMaterialEntity::getDemandId, demandId));
                if (e == null) {
                    writeExt(demandId, typeCode, ext);
                    return;
                }
                if (ext.containsKey("materialSubtype")) e.setMaterialSubtype(asString(ext.get("materialSubtype")));
                if (ext.containsKey("usageScenario")) e.setUsageScenario(asString(ext.get("usageScenario")));
                if (ext.containsKey("quantity")) e.setQuantity(asInteger(ext.get("quantity")));
                if (ext.containsKey("expectedArrivalAt")) e.setExpectedArrivalAt(asDateTime(ext.get("expectedArrivalAt")));
                materialMapper.updateById(e);
            }
            case "TRAIN" -> {
                DemandExtTrainingEntity e = trainingMapper.selectOne(new LambdaQueryWrapper<DemandExtTrainingEntity>()
                        .eq(DemandExtTrainingEntity::getDemandId, demandId));
                if (e == null) {
                    writeExt(demandId, typeCode, ext);
                    return;
                }
                if (ext.containsKey("trainingSubtype")) e.setTrainingSubtype(asString(ext.get("trainingSubtype")));
                if (ext.containsKey("traineeObject")) e.setTraineeObject(asString(ext.get("traineeObject")));
                if (ext.containsKey("traineeCount")) e.setTraineeCount(asInteger(ext.get("traineeCount")));
                if (ext.containsKey("expectedCompleteAt")) e.setExpectedCompleteAt(asDateTime(ext.get("expectedCompleteAt")));
                trainingMapper.updateById(e);
            }
            default -> throw new BizException(ErrorCode.DEMAND_TYPE_INVALID, "不支持的需求类型: " + typeCode);
        }
    }

    /** 详情拼装：按类型读扩展行（无则 null） */
    public Object readExt(Long demandId, String typeCode) {
        return switch (typeCode) {
            case "TECH" -> techMapper.selectOne(new LambdaQueryWrapper<DemandExtTechEntity>()
                    .eq(DemandExtTechEntity::getDemandId, demandId));
            case "MATL" -> materialMapper.selectOne(new LambdaQueryWrapper<DemandExtMaterialEntity>()
                    .eq(DemandExtMaterialEntity::getDemandId, demandId));
            case "TRAIN" -> trainingMapper.selectOne(new LambdaQueryWrapper<DemandExtTrainingEntity>()
                    .eq(DemandExtTrainingEntity::getDemandId, demandId));
            default -> null;
        };
    }

    /** 删除扩展行（类型修正时清理旧类型扩展数据） */
    public void removeExt(Long demandId, String typeCode) {
        switch (typeCode) {
            case "TECH" -> techMapper.delete(new LambdaQueryWrapper<DemandExtTechEntity>()
                    .eq(DemandExtTechEntity::getDemandId, demandId));
            case "MATL" -> materialMapper.delete(new LambdaQueryWrapper<DemandExtMaterialEntity>()
                    .eq(DemandExtMaterialEntity::getDemandId, demandId));
            case "TRAIN" -> trainingMapper.delete(new LambdaQueryWrapper<DemandExtTrainingEntity>()
                    .eq(DemandExtTrainingEntity::getDemandId, demandId));
            default -> {
            }
        }
    }

    private static String asString(Object v) {
        return v == null ? null : String.valueOf(v);
    }

    private static Integer asInteger(Object v) {
        if (v == null) {
            return null;
        }
        if (v instanceof Number n) {
            return n.intValue();
        }
        return Integer.valueOf(String.valueOf(v));
    }

    private static LocalDateTime asDateTime(Object v) {
        if (v == null) {
            return null;
        }
        String s = String.valueOf(v).trim();
        if (s.isEmpty()) {
            return null;
        }
        if (s.length() == 10) {
            s = s + " 00:00:00";
        }
        // 兼容 ISO（yyyy-MM-dd'T'HH:mm:ss）与空格分隔两种格式
        return LocalDateTime.parse(s.replace('T', ' '), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
    }
}

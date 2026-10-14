package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 组织镜像查询辅助：orgId → 组织名（列表/详情拼装用）。
 */
@Service
public class OrgLookupService {

    private final OrgSnapshotViewMapper orgSnapshotMapper;

    public OrgLookupService(OrgSnapshotViewMapper orgSnapshotMapper) {
        this.orgSnapshotMapper = orgSnapshotMapper;
    }

    public String nameOf(Long orgId) {
        if (orgId == null) {
            return null;
        }
        OrgSnapshotView org = orgSnapshotMapper.selectOne(new LambdaQueryWrapper<OrgSnapshotView>()
                .eq(OrgSnapshotView::getId, orgId));
        return org == null ? String.valueOf(orgId) : org.getName();
    }

    public Map<Long, String> namesOf(Collection<Long> orgIds) {
        if (orgIds == null || orgIds.isEmpty()) {
            return Collections.emptyMap();
        }
        return orgSnapshotMapper.selectList(new LambdaQueryWrapper<OrgSnapshotView>()
                        .in(OrgSnapshotView::getId, orgIds.stream().filter(Objects::nonNull).distinct().toList()))
                .stream()
                .collect(Collectors.toMap(OrgSnapshotView::getOrgId, OrgSnapshotView::getName, (a, b) -> a));
    }
}

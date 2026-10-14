package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.mapper.UserSnapshotViewMapper;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 用户查询辅助：批量解析用户数值 ID → 姓名（详情/日志拼装用）。
 * deptPath（部门名称路径）不落表，按组织树物化路径派生填充。
 */
@Service
public class UserLookupService {

    private final UserSnapshotViewMapper userSnapshotMapper;
    private final OrgSnapshotViewMapper orgSnapshotMapper;

    public UserLookupService(UserSnapshotViewMapper userSnapshotMapper,
                             OrgSnapshotViewMapper orgSnapshotMapper) {
        this.userSnapshotMapper = userSnapshotMapper;
        this.orgSnapshotMapper = orgSnapshotMapper;
    }

    public String nameOf(Long id) {
        if (id == null) {
            return null;
        }
        UserSnapshotView user = userSnapshotMapper.selectById(id);
        return user == null ? String.valueOf(id) : user.getName();
    }

    public Map<Long, String> namesOf(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return Collections.emptyMap();
        }
        return userSnapshotMapper.selectBatchIds(ids.stream().filter(Objects::nonNull).distinct().toList())
                .stream()
                .collect(Collectors.toMap(UserSnapshotView::getId, UserSnapshotView::getName, (a, b) -> a));
    }

    public UserSnapshotView getById(Long id) {
        if (id == null) {
            return null;
        }
        UserSnapshotView user = userSnapshotMapper.selectById(id);
        if (user != null) {
            fillDeptPath(user);
        }
        return user;
    }

    public Map<Long, UserSnapshotView> mapOf(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<Long, UserSnapshotView> map = userSnapshotMapper
                .selectBatchIds(ids.stream().filter(Objects::nonNull).distinct().toList())
                .stream()
                .collect(Collectors.toMap(UserSnapshotView::getId, Function.identity(), (a, b) -> a));
        map.values().forEach(this::fillDeptPath);
        return map;
    }

    public boolean exists(Long id) {
        return id != null && userSnapshotMapper.selectById(id) != null;
    }

    public LambdaQueryWrapper<UserSnapshotView> wrapper() {
        return new LambdaQueryWrapper<>();
    }

    /** 部门名称路径由组织树物化 path 派生（如 创金合信零售业务线/财管科技产品部） */
    private void fillDeptPath(UserSnapshotView user) {
        user.setDeptPath(buildDeptPath(user.getPrimaryOrgId()));
    }

    private String buildDeptPath(Long orgId) {
        if (orgId == null) {
            return null;
        }
        OrgSnapshotView org = orgSnapshotMapper.selectById(orgId);
        if (org == null || org.getPath() == null) {
            return null;
        }
        Map<Long, String> names = orgSnapshotMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshotView::getId, OrgSnapshotView::getName, (a, b) -> a));
        StringBuilder sb = new StringBuilder();
        for (String id : org.getPath().split("/")) {
            if (id.isBlank()) {
                continue;
            }
            String name = names.get(Long.parseLong(id));
            if (name != null) {
                if (sb.length() > 0) {
                    sb.append("/");
                }
                sb.append(name);
            }
        }
        return sb.length() == 0 ? null : sb.toString();
    }
}

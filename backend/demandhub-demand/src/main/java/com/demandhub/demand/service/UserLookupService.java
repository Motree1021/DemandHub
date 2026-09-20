package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.UserSnapshotViewMapper;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 用户镜像查询辅助：批量解析用户数值 ID → 姓名（详情/日志拼装用）。
 */
@Service
public class UserLookupService {

    private final UserSnapshotViewMapper userSnapshotMapper;

    public UserLookupService(UserSnapshotViewMapper userSnapshotMapper) {
        this.userSnapshotMapper = userSnapshotMapper;
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
        return id == null ? null : userSnapshotMapper.selectById(id);
    }

    public Map<Long, UserSnapshotView> mapOf(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return Collections.emptyMap();
        }
        return userSnapshotMapper.selectBatchIds(ids.stream().filter(Objects::nonNull).distinct().toList())
                .stream()
                .collect(Collectors.toMap(UserSnapshotView::getId, Function.identity(), (a, b) -> a));
    }

    public boolean exists(Long id) {
        return id != null && userSnapshotMapper.selectById(id) != null;
    }

    public LambdaQueryWrapper<UserSnapshotView> wrapper() {
        return new LambdaQueryWrapper<>();
    }
}

package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.entity.RoleGrantView;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.mapper.RoleGrantViewMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 数据范围计算（FR-M1-04）：
 * 角色 → 授权组织子树（物化路径前缀匹配）→ 需求查询过滤条件。
 * 结果缓存 Redis 60 秒，授权调整 1 分钟内生效（FR-M1-03 验收）。
 */
@Service
public class DataScopeService {

    private static final String CACHE_KEY = "scope:";
    private static final Duration CACHE_TTL = Duration.ofSeconds(60);

    private final RoleGrantViewMapper grantMapper;
    private final OrgSnapshotViewMapper orgMapper;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DataScopeService(RoleGrantViewMapper grantMapper,
                            OrgSnapshotViewMapper orgMapper,
                            StringRedisTemplate redis) {
        this.grantMapper = grantMapper;
        this.orgMapper = orgMapper;
        this.redis = redis;
    }

    /**
     * 计算当前用户数据范围（带 60s 缓存）
     */
    public DataScope currentScope(CurrentUser user) {
        DataScope cached = loadCache(user.getUserId());
        if (cached != null) {
            return cached;
        }
        DataScope scope = compute(user);
        saveCache(user.getUserId(), scope);
        return scope;
    }

    private DataScope compute(CurrentUser user) {
        LocalDateTime now = LocalDateTime.now();
        List<RoleGrantView> grants = grantMapper.selectList(new LambdaQueryWrapper<RoleGrantView>()
                .eq(RoleGrantView::getDemandUserId, user.getId())
                .and(w -> w.isNull(RoleGrantView::getEffectiveFrom).or().le(RoleGrantView::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrantView::getEffectiveTo).or().ge(RoleGrantView::getEffectiveTo, now)));

        Set<String> roles = grants.stream().map(RoleGrantView::getRoleCode).collect(Collectors.toSet());
        // 需求管理者：全零售线
        if (roles.contains("EXECUTIVE")) {
            return DataScope.bypass();
        }

        DataScope scope = new DataScope();
        scope.setUserId(user.getId());
        // 角色族版（D1）：不设提报人角色，任何登录用户均可看自己提报的需求
        scope.setReporter(true);

        // 仅系统管理员/无业务角色：不参与业务流，仅提报人范围
        roles.remove("ADMIN");
        if (roles.isEmpty()) {
            return scope;
        }

        // HANDLER / MANAGER：授权组织子树并集
        Set<Long> grantedOrgIds = grants.stream()
                .filter(g -> "HANDLER".equals(g.getRoleCode()) || "MANAGER".equals(g.getRoleCode()))
                .map(RoleGrantView::getOrgId)
                .filter(java.util.Objects::nonNull)
                .collect(Collectors.toSet());
        if (!grantedOrgIds.isEmpty()) {
            Map<Long, OrgSnapshotView> all = orgMapper.selectList(null).stream()
                    .collect(Collectors.toMap(OrgSnapshotView::getOrgId, Function.identity()));
            for (Long orgId : grantedOrgIds) {
                OrgSnapshotView root = all.get(orgId);
                if (root == null) {
                    continue;
                }
                String prefix = root.getPath();
                all.values().stream()
                        .filter(o -> o.getPath() != null && o.getPath().startsWith(prefix))
                        .forEach(o -> scope.getOrgIds().add(o.getOrgId()));
            }
        }
        return scope;
    }

    /**
     * 生成需求表过滤 SQL 片段（不带 WHERE 关键字）；返回 null 表示不过滤
     */
    public String buildCondition(DataScope scope, String columnPrefix) {
        if (scope.isBypass()) {
            return null;
        }
        if (scope.isNoAccess()) {
            return "1 = 0";
        }
        String prefix = columnPrefix == null ? "" : columnPrefix;
        List<String> parts = new ArrayList<>();
        if (!scope.getOrgIds().isEmpty()) {
            parts.add(prefix + "assignee_org_id IN ("
                    + scope.getOrgIds().stream().map(String::valueOf).collect(Collectors.joining(","))
                    + ")");
        }
        if (scope.isReporter()) {
            parts.add(prefix + "submitter_id = " + scope.getUserId());
        }
        if (parts.isEmpty()) {
            return "1 = 0";
        }
        return parts.size() == 1 ? parts.get(0) : "(" + String.join(" OR ", parts) + ")";
    }

    private DataScope loadCache(String userId) {
        try {
            String json = redis.opsForValue().get(CACHE_KEY + userId);
            return json == null ? null : objectMapper.readValue(json, DataScope.class);
        } catch (Exception e) {
            return null;
        }
    }

    private void saveCache(String userId, DataScope scope) {
        try {
            redis.opsForValue().set(CACHE_KEY + userId, objectMapper.writeValueAsString(scope), CACHE_TTL);
        } catch (Exception ignored) {
            // 缓存失败不影响主流程
        }
    }
}

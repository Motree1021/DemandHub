package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.entity.RoleGrantView;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.mapper.RoleGrantViewMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 数据范围计算（FR-M1-05，角色族三维版：角色族 × 组织子树 × 类型集合）：
 * 角色 → 授权类型集合 × 授权组织子树（物化路径前缀匹配）→ 需求查询过滤条件。
 * 缓存键含授权版本号（count + max(updated_at)），授权变更即时失效重算（FR-M1-03：1 分钟内生效）。
 */
@Service
public class DataScopeService {

    private static final String CACHE_KEY = "scope:";
    private static final Duration CACHE_TTL = Duration.ofSeconds(60);
    /** 类型码白名单（拼 SQL 防注入，类型码来自 demand_type 字典） */
    private static final Pattern TYPE_CODE_PATTERN = Pattern.compile("^[A-Z0-9_]+$");

    private final RoleGrantViewMapper grantMapper;
    private final OrgSnapshotViewMapper orgMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DataScopeService(RoleGrantViewMapper grantMapper,
                            OrgSnapshotViewMapper orgMapper,
                            DemandTypeMapper demandTypeMapper,
                            StringRedisTemplate redis) {
        this.grantMapper = grantMapper;
        this.orgMapper = orgMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.redis = redis;
    }

    /**
     * 计算当前用户数据范围（缓存键含授权版本，授权变更即时重算）
     */
    public DataScope currentScope(CurrentUser user) {
        String version = grantVersion(user.getId());
        DataScope cached = loadCache(user.getUserId(), version);
        if (cached != null) {
            return cached;
        }
        DataScope scope = compute(user);
        saveCache(user.getUserId(), version, scope);
        return scope;
    }

    /** 授权版本（count + max(updated_at)）：授权新增/变更/回收均改变版本 */
    private String grantVersion(Long userId) {
        try {
            Map<String, Object> row = grantMapper.grantVersion(userId);
            if (row == null) {
                return "0";
            }
            return row.get("cnt") + "@" + row.get("ver");
        } catch (Exception e) {
            return String.valueOf(System.currentTimeMillis());
        }
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
        // ADMIN 超级用户：全线直通（产品决策：放行全部业务操作与数据范围）
        if (roles.contains("ADMIN")) {
            return DataScope.bypass();
        }

        DataScope scope = new DataScope();
        scope.setUserId(user.getId());
        // 角色族版（D1）：不设提报人角色，任何登录用户均可看自己提报的需求
        scope.setReporter(true);

        // 无业务角色：不参与业务流，仅提报人范围
        if (roles.isEmpty()) {
            return scope;
        }

        // HANDLER / MANAGER：类型集合 × 授权组织子树（三维：角色族 × 组织 × 类型）
        List<RoleGrantView> bizGrants = grants.stream()
                .filter(g -> "HANDLER".equals(g.getRoleCode()) || "MANAGER".equals(g.getRoleCode()))
                .filter(g -> g.getOrgId() != null)
                .toList();
        if (bizGrants.isEmpty()) {
            return scope;
        }
        Map<Long, OrgSnapshotView> all = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshotView::getOrgId, Function.identity()));
        for (RoleGrantView grant : bizGrants) {
            OrgSnapshotView root = all.get(grant.getOrgId());
            if (root == null || root.getPath() == null) {
                continue;
            }
            String prefix = root.getPath();
            Set<Long> subtree = all.values().stream()
                    .filter(o -> o.getPath() != null && o.getPath().startsWith(prefix))
                    .map(OrgSnapshotView::getOrgId)
                    .collect(Collectors.toSet());
            for (String typeCode : scopeTypes(grant)) {
                scope.getOrgIdsByType().computeIfAbsent(typeCode, k -> new TreeSet<>()).addAll(subtree);
            }
        }
        return scope;
    }

    /** 授权的类型集合：NULL/空 = 跟随角色默认（全部启用类型）；否则按逗号拆分 */
    private Set<String> scopeTypes(RoleGrantView grant) {
        if (!StringUtils.hasText(grant.getDemandTypeScope())) {
            return demandTypeMapper.selectList(new LambdaQueryWrapper<DemandTypeEntity>()
                            .eq(DemandTypeEntity::getStatus, "ACTIVE")).stream()
                    .map(DemandTypeEntity::getTypeCode).collect(Collectors.toSet());
        }
        return List.of(grant.getDemandTypeScope().split(",")).stream()
                .map(String::trim).filter(StringUtils::hasText).collect(Collectors.toSet());
    }

    /**
     * 生成需求表过滤 SQL 片段（不带 WHERE 关键字）；返回 null 表示不过滤。
     * 口径：逐类型 (demand_type_code = ? AND assignee_org_id IN (...)) 取并集，再与提报人视角取并。
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
        if (!scope.getOrgIdsByType().isEmpty()) {
            List<String> typeParts = new ArrayList<>();
            scope.getOrgIdsByType().forEach((typeCode, orgIds) -> {
                if (orgIds.isEmpty() || !TYPE_CODE_PATTERN.matcher(typeCode).matches()) {
                    return;
                }
                typeParts.add("(" + prefix + "demand_type_code = '" + typeCode + "' AND "
                        + prefix + "assignee_org_id IN ("
                        + orgIds.stream().map(String::valueOf).collect(Collectors.joining(","))
                        + "))");
            });
            if (!typeParts.isEmpty()) {
                parts.add("(" + String.join(" OR ", typeParts) + ")");
            }
        }
        if (scope.isReporter()) {
            parts.add(prefix + "submitter_id = " + scope.getUserId());
        }
        if (parts.isEmpty()) {
            return "1 = 0";
        }
        return parts.size() == 1 ? parts.get(0) : "(" + String.join(" OR ", parts) + ")";
    }

    private DataScope loadCache(String userId, String version) {
        try {
            String json = redis.opsForValue().get(CACHE_KEY + userId + ":" + version);
            return json == null ? null : objectMapper.readValue(json, DataScope.class);
        } catch (Exception e) {
            return null;
        }
    }

    private void saveCache(String userId, String version, DataScope scope) {
        try {
            redis.opsForValue().set(CACHE_KEY + userId + ":" + version,
                    objectMapper.writeValueAsString(scope), CACHE_TTL);
        } catch (Exception ignored) {
            // 缓存失败不影响主流程
        }
    }
}

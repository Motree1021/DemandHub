package com.demandhub.demand.service;

import com.demandhub.common.context.CurrentUser;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.entity.RoleGrantView;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.mapper.RoleGrantViewMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 数据范围（权限矩阵）单测（P7 任务 7.1，FR-M1-05 角色族三维版）：
 * 角色族 × 组织子树 × 类型集合 → SQL 过滤片段。
 * EXECUTIVE 全线直通 / ADMIN 与无角色仅提报人 / MANAGER·HANDLER 按授权组织子树×类型；
 * 类型码白名单防注入；授权版本缓存命中不重算。
 */
@ExtendWith(MockitoExtension.class)
class DataScopeServiceTest {

    @Mock
    private RoleGrantViewMapper grantMapper;
    @Mock
    private OrgSnapshotViewMapper orgMapper;
    @Mock
    private DemandTypeMapper demandTypeMapper;
    @Mock
    private StringRedisTemplate redis;
    @InjectMocks
    private DataScopeService dataScopeService;

    @SuppressWarnings("unchecked")
    private final ValueOperations<String, String> valueOps = mock(ValueOperations.class);

    @BeforeEach
    void setUpCacheMiss() {
        // 授权版本固定 + 缓存未命中（各用例公共）
        lenient().when(grantMapper.grantVersion(1003L)).thenReturn(Map.of("cnt", 2, "ver", 100));
        lenient().when(redis.opsForValue()).thenReturn(valueOps);
        lenient().when(valueOps.get(anyString())).thenReturn(null);
    }

    private static CurrentUser user() {
        CurrentUser u = new CurrentUser();
        u.setId(1003L);
        u.setUserId("1003");
        return u;
    }

    private static RoleGrantView grant(String roleCode, Long orgId, String typeScope) {
        RoleGrantView g = new RoleGrantView();
        g.setDemandUserId(1003L);
        g.setRoleCode(roleCode);
        g.setOrgId(orgId);
        g.setDemandTypeScope(typeScope);
        return g;
    }

    private static OrgSnapshotView org(Long orgId, String path) {
        OrgSnapshotView o = new OrgSnapshotView();
        // getOrgId() 同义于 id（setOrgId 为 no-op 兼容旧代码），须用 setId
        o.setId(orgId);
        o.setPath(path);
        return o;
    }

    private static DemandTypeEntity type(String code) {
        DemandTypeEntity t = new DemandTypeEntity();
        t.setTypeCode(code);
        t.setStatus("ACTIVE");
        return t;
    }

    @Test
    void executive_bypassesAllFiltering() {
        when(grantMapper.selectList(any())).thenReturn(List.of(grant("EXECUTIVE", 1L, null)));

        DataScope scope = dataScopeService.currentScope(user());

        assertTrue(scope.isBypass());
    }

    @Test
    void adminOnly_reporterOnlyNoBusinessScope() {
        when(grantMapper.selectList(any())).thenReturn(List.of(grant("ADMIN", null, null)));

        DataScope scope = dataScopeService.currentScope(user());

        assertFalse(scope.isBypass());
        assertTrue(scope.isReporter());
        assertTrue(scope.getOrgIdsByType().isEmpty());
        assertEquals(1003L, scope.getUserId());
    }

    @Test
    void noGrants_reporterOnly() {
        when(grantMapper.selectList(any())).thenReturn(List.of());

        DataScope scope = dataScopeService.currentScope(user());

        assertFalse(scope.isBypass());
        assertTrue(scope.isReporter());
        assertTrue(scope.getOrgIdsByType().isEmpty());
    }

    @Test
    void managerGrant_typeScopedOrgSubtreePrefixMatch() {
        when(grantMapper.selectList(any())).thenReturn(List.of(grant("MANAGER", 110L, "TECH")));
        // 物化路径子树：110 及子孙 111；121 属另一分支
        when(orgMapper.selectList(null)).thenReturn(List.of(
                org(110L, "/110/"), org(111L, "/110/111/"), org(121L, "/121/")));

        DataScope scope = dataScopeService.currentScope(user());

        assertTrue(scope.isReporter(), "任何登录用户均含提报人视角");
        assertEquals(new TreeSet<>(Set.of(110L, 111L)), scope.getOrgIdsByType().get("TECH"));
        assertNull(scope.getOrgIdsByType().get("MATL"));
        assertEquals(Set.of(110L, 111L), scope.unionOrgIds());
    }

    @Test
    void handlerGrant_nullTypeScope_followsAllActiveTypes() {
        when(grantMapper.selectList(any())).thenReturn(List.of(grant("HANDLER", 121L, null)));
        when(orgMapper.selectList(null)).thenReturn(List.of(org(121L, "/121/")));
        when(demandTypeMapper.selectList(any())).thenReturn(List.of(type("TECH"), type("MATL")));

        DataScope scope = dataScopeService.currentScope(user());

        assertEquals(Set.of(121L), scope.getOrgIdsByType().get("TECH"));
        assertEquals(Set.of(121L), scope.getOrgIdsByType().get("MATL"));
    }

    @Test
    void bizGrantWithoutOrg_ignored() {
        when(grantMapper.selectList(any())).thenReturn(List.of(grant("MANAGER", null, "TECH")));

        DataScope scope = dataScopeService.currentScope(user());

        assertTrue(scope.getOrgIdsByType().isEmpty());
    }

    @Test
    void cacheHit_skipsRecompute() {
        // 缓存键含授权版本（count@maxUpdatedAt），命中直接用缓存
        when(valueOps.get("scope:1003:2@100"))
                .thenReturn("{\"bypass\":true,\"noAccess\":false,\"userId\":null,"
                        + "\"reporter\":false,\"orgIdsByType\":{}}");

        DataScope scope = dataScopeService.currentScope(user());

        assertTrue(scope.isBypass());
        verify(grantMapper, never()).selectList(any());
    }

    // ---------- buildCondition：SQL 片段生成（纯函数，直接构造 DataScope） ----------

    @Test
    void buildCondition_bypass_returnsNull() {
        assertNull(dataScopeService.buildCondition(DataScope.bypass(), null));
    }

    @Test
    void buildCondition_noAccess_returnsAlwaysFalse() {
        assertEquals("1 = 0", dataScopeService.buildCondition(DataScope.noAccess(), null));
    }

    @Test
    void buildCondition_reporterOnly_filtersBySubmitter() {
        DataScope scope = new DataScope();
        scope.setUserId(1003L);
        scope.setReporter(true);

        assertEquals("submitter_id = 1003", dataScopeService.buildCondition(scope, null));
    }

    @Test
    void buildCondition_typeScopedUnionsWithReporter_andAppliesPrefix() {
        DataScope scope = new DataScope();
        scope.setUserId(1003L);
        scope.setReporter(true);
        scope.getOrgIdsByType().put("TECH", new TreeSet<>(Set.of(110L, 111L)));
        scope.getOrgIdsByType().put("MATL", new TreeSet<>(Set.of(121L)));

        String sql = dataScopeService.buildCondition(scope, "d.");

        assertTrue(sql.contains("(d.demand_type_code = 'TECH' AND d.assignee_org_id IN (110,111))"), sql);
        assertTrue(sql.contains("(d.demand_type_code = 'MATL' AND d.assignee_org_id IN (121))"), sql);
        assertTrue(sql.contains("d.submitter_id = 1003"), sql);
        assertTrue(sql.contains(" OR "), "类型并集与提报人视角取并: " + sql);
    }

    @Test
    void buildCondition_maliciousTypeCode_filteredByWhitelist() {
        DataScope scope = new DataScope();
        scope.setUserId(1003L);
        scope.setReporter(true);
        // 注入式类型码必须被白名单过滤，不得拼入 SQL
        scope.getOrgIdsByType().put("TECH' OR '1'='1", new TreeSet<>(Set.of(110L)));

        String sql = dataScopeService.buildCondition(scope, null);

        assertEquals("submitter_id = 1003", sql);
    }

    @Test
    void buildCondition_emptyScope_returnsAlwaysFalse() {
        DataScope scope = new DataScope();

        assertEquals("1 = 0", dataScopeService.buildCondition(scope, null));
    }
}

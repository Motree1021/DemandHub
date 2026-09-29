package com.demandhub.system.service;

import com.demandhub.system.entity.ChannelUserMapping;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelUserMappingMapper;
import com.demandhub.system.sso.SsoProfile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * OneID 匹配引擎单测（P7 任务 7.1，FR-M1-01）。
 * 匹配优先级：既有渠道映射 → 手机号精确 > 企微 userid → 未命中自动建号（D4）；
 * MERGED 用户自动跳转目标；冲突记录 conflictUserId 不阻塞登录；部门未映射回流校准清单。
 */
@ExtendWith(MockitoExtension.class)
class ChannelUserMatcherTest {

    private static final String CHANNEL = "CHUANGJIN_LS";

    @Mock
    private UserService userService;
    @Mock
    private ChannelUserMappingMapper mappingMapper;
    @Mock
    private ChannelDeptCalibrateService deptCalibrateService;
    @InjectMocks
    private ChannelUserMatcher matcher;

    private static SsoProfile profile(String userId, String name, String phone, String deptId) {
        SsoProfile p = new SsoProfile();
        p.setUserId(userId);
        p.setName(name);
        p.setPhone(phone);
        p.setDeptId(deptId);
        return p;
    }

    private static UserSnapshot user(Long id, String status) {
        UserSnapshot u = new UserSnapshot();
        u.setId(id);
        u.setStatus(status);
        return u;
    }

    private static ChannelUserMapping mapping(Long id, Long demandUserId, String matchType) {
        ChannelUserMapping m = new ChannelUserMapping();
        m.setId(id);
        m.setChannelCode(CHANNEL);
        m.setChannelUserId("wq_u_001");
        m.setDemandUserId(demandUserId);
        m.setMatchType(matchType);
        return m;
    }

    @Test
    void existingMappingHit_refreshesSnapshotAndTouchLogin() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", null);
        ChannelUserMapping m = mapping(1L, 7L, "WECOMID");
        when(mappingMapper.selectOne(any())).thenReturn(m);
        when(userService.findById(7L)).thenReturn(user(7L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(7L, result.getUser().getId());
        assertEquals("WECOMID", result.getMatchType());
        assertNull(result.getConflictUserId());
        // 命中后刷新渠道侧快照
        verify(mappingMapper).updateById(argThat((ChannelUserMapping x) ->
                "张三".equals(x.getChannelName()) && "13800001111".equals(x.getChannelPhone())));
        verify(userService).touchLastLogin(7L, CHANNEL);
    }

    @Test
    void existingMappingHit_phonePointsToAnotherOneID_recordsConflict() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", null);
        when(mappingMapper.selectOne(any())).thenReturn(mapping(1L, 7L, "WECOMID"));
        when(userService.findById(7L)).thenReturn(user(7L, "ACTIVE"));
        // 同手机号命中另一个 OneID → 合并提示，不阻塞登录
        when(userService.findByPhone("13800001111")).thenReturn(user(9L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(7L, result.getUser().getId());
        assertEquals(9L, result.getConflictUserId());
    }

    @Test
    void mappingPointsToMergedUser_followsTargetAndRepointsMapping() {
        SsoProfile p = profile("wq_u_001", "张三", null, null);
        ChannelUserMapping m = mapping(1L, 7L, "WECOMID");
        when(mappingMapper.selectOne(any())).thenReturn(m);
        UserSnapshot merged = user(7L, "MERGED");
        merged.setMergedToUserId(8L);
        when(userService.findById(7L)).thenReturn(merged);
        when(userService.findById(8L)).thenReturn(user(8L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(8L, result.getUser().getId());
        // 映射随之一并改指目标 OneID（followMerged 改指 + refreshMappingSnapshot 刷新快照，共 2 次落库）
        verify(mappingMapper, times(2)).updateById(argThat((ChannelUserMapping x) ->
                Long.valueOf(8L).equals(x.getDemandUserId())));
        verify(userService).touchLastLogin(8L, CHANNEL);
    }

    @Test
    void noMapping_phoneExactMatch_createsPhoneMapping() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", null);
        when(userService.findByPhone("13800001111")).thenReturn(user(5L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(5L, result.getUser().getId());
        assertEquals("PHONE", result.getMatchType());
        // 手机号精确匹配优先于企微 userid
        verify(mappingMapper).insert(argThat((ChannelUserMapping x) ->
                "PHONE".equals(x.getMatchType()) && Long.valueOf(5L).equals(x.getDemandUserId())));
        verify(userService).touchLastLogin(5L, CHANNEL);
    }

    @Test
    void noMapping_phoneAndWecomHitDifferentOneIDs_phoneWinsAndRecordsConflict() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", null);
        when(userService.findByPhone("13800001111")).thenReturn(user(5L, "ACTIVE"));
        when(userService.findByWecomUserid("wq_u_001")).thenReturn(user(6L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(5L, result.getUser().getId());
        assertEquals("PHONE", result.getMatchType());
        assertEquals(6L, result.getConflictUserId());
    }

    @Test
    void noMapping_noPhone_wecomUseridMatch_createsWecomMapping() {
        SsoProfile p = profile("wq_u_001", "张三", null, null);
        when(userService.findByWecomUserid("wq_u_001")).thenReturn(user(6L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(6L, result.getUser().getId());
        assertEquals("WECOMID", result.getMatchType());
        verify(mappingMapper).insert(argThat((ChannelUserMapping x) ->
                "WECOMID".equals(x.getMatchType()) && Long.valueOf(6L).equals(x.getDemandUserId())));
    }

    @Test
    void noMatch_withUserId_autoCreatesActiveAccountAndMapping() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", "D100");
        OrgSnapshot org = new OrgSnapshot();
        org.setId(121L);
        when(userService.findOrgByExternalDeptId("D100")).thenReturn(org);
        UserSnapshot created = user(20L, "ACTIVE");
        when(userService.createChannelUser("张三", "13800001111", "wq_u_001", 121L, true))
                .thenReturn(created);

        MatchResult result = matcher.match(CHANNEL, p);

        assertTrue(result.isCreatedNew());
        assertEquals("WECOMID", result.getMatchType());
        assertEquals(20L, result.getUser().getId());
        verify(mappingMapper).insert(argThat((ChannelUserMapping x) -> Long.valueOf(20L).equals(x.getDemandUserId())));
    }

    @Test
    void noMatch_withoutUserId_createsPendingAccountWithoutMapping() {
        // 无手机且无 userid 的字段缺失票据：只兜 PENDING，不建映射（MANUAL 绑定后激活）
        SsoProfile p = profile(null, "张三", null, null);
        UserSnapshot created = user(21L, "PENDING");
        when(userService.createChannelUser("张三", null, null, UserService.EXTERNAL_ORG_ID, false))
                .thenReturn(created);

        MatchResult result = matcher.match(CHANNEL, p);

        assertTrue(result.isCreatedNew());
        assertEquals("MANUAL", result.getMatchType());
        verify(mappingMapper, never()).insert(any(ChannelUserMapping.class));
    }

    @Test
    void deptNotMapped_recordsCalibrationAndHangsExternalOrg() {
        SsoProfile p = profile("wq_u_001", "张三", null, "D999");
        // 部门未映射：回流校准清单（不阻塞登录），自动建号挂外部虚拟组织 900
        when(userService.findOrgByExternalDeptId("D999")).thenReturn(null);
        UserSnapshot created = user(22L, "ACTIVE");
        when(userService.createChannelUser("张三", null, "wq_u_001", UserService.EXTERNAL_ORG_ID, true))
                .thenReturn(created);

        MatchResult result = matcher.match(CHANNEL, p);

        verify(deptCalibrateService).record(CHANNEL, p);
        assertEquals(22L, result.getUser().getId());
    }

    @Test
    void deptMapped_skipsCalibration() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", "D100");
        OrgSnapshot org = new OrgSnapshot();
        org.setId(121L);
        when(userService.findOrgByExternalDeptId("D100")).thenReturn(org);
        when(userService.findByPhone("13800001111")).thenReturn(user(5L, "ACTIVE"));

        matcher.match(CHANNEL, p);

        verify(deptCalibrateService, never()).record(anyString(), any());
    }

    @Test
    void mergedUserFoundByPhone_followsTarget() {
        SsoProfile p = profile("wq_u_001", "张三", "13800001111", null);
        UserSnapshot merged = user(7L, "MERGED");
        merged.setMergedToUserId(8L);
        when(userService.findByPhone("13800001111")).thenReturn(merged);
        when(userService.findById(8L)).thenReturn(user(8L, "ACTIVE"));

        MatchResult result = matcher.match(CHANNEL, p);

        assertEquals(8L, result.getUser().getId());
        assertEquals("PHONE", result.getMatchType());
        ArgumentCaptor<ChannelUserMapping> captor = ArgumentCaptor.forClass(ChannelUserMapping.class);
        verify(mappingMapper).insert(captor.capture());
        assertEquals(8L, captor.getValue().getDemandUserId());
    }
}

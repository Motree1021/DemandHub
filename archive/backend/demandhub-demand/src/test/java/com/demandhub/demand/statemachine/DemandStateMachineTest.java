package com.demandhub.demand.statemachine;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.UserSnapshotViewMapper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 状态机族鉴权单测（P7 任务 7.1，架构 4.1 + P4 角色族）。
 * 五档角色门禁（ANY_AUTHENTICATED / MANAGER / HANDLER / HANDLER_OR_MANAGER / EXECUTIVE_ONLY）
 * 基于代码内置 DEFAULT 流转表；另覆盖非法流转、乐观锁并发冲突、HOLD/RESUME 叠加态、
 * 流转日志与领域事件落库。
 */
@ExtendWith(MockitoExtension.class)
class DemandStateMachineTest {

    @Mock
    private DemandMapper demandMapper;
    @Mock
    private DemandTransitionLogMapper transitionLogMapper;
    @Mock
    private DemandTypeMapper demandTypeMapper;
    @Mock
    private UserSnapshotViewMapper userSnapshotMapper;
    @Mock
    private ApplicationEventPublisher eventPublisher;

    private DemandStateMachine stateMachine;

    @BeforeAll
    static void initMybatisPlusLambdaCache() {
        // LambdaUpdateWrapper.set() 即时解析方法引用，依赖 MP TableInfo lambda 缓存；
        // 纯单测无 SqlSessionFactory 引导，需手工注册实体元数据
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), ""), DemandEntity.class);
    }

    @BeforeEach
    void setUp() {
        // 真实配置（代码内置 DEFAULT 流转表）+ mock 持久层
        stateMachine = new DemandStateMachine(new StateMachineConfig(),
                demandMapper, transitionLogMapper, demandTypeMapper, userSnapshotMapper, eventPublisher);
        // 类型未配置自定义状态机 → DEFAULT（lenient：部分用例不触达）
        lenient().when(demandTypeMapper.selectOne(any())).thenReturn(null);
    }

    private static DemandEntity demand(String status) {
        DemandEntity d = new DemandEntity();
        d.setId(1L);
        d.setDemandNo("TECH-20260923-001");
        d.setTitle("测试需求");
        d.setDemandTypeCode("TECH");
        d.setStatus(status);
        d.setOnHold(0);
        d.setVersion(1);
        return d;
    }

    private static CurrentUser operator(String... roles) {
        CurrentUser u = new CurrentUser();
        u.setId(1003L);
        u.setUserId("1003");
        u.setRoles(List.of(roles));
        return u;
    }

    private static BizException assertBiz(org.junit.jupiter.api.function.Executable exec, ErrorCode code) {
        BizException ex = assertThrows(BizException.class, exec);
        assertEquals(code.getCode(), ex.getCode());
        return ex;
    }

    // ---------- canTransit：五档角色门禁 ----------

    @Test
    void canTransit_managerGate_accept() {
        DemandEntity d = demand("SUBMITTED");
        assertTrue(stateMachine.canTransit(d, DemandEvent.ACCEPT, operator("MANAGER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.ACCEPT, operator("HANDLER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.ACCEPT, operator("EXECUTIVE")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.ACCEPT, operator()));
    }

    @Test
    void canTransit_handlerGate_claim() {
        DemandEntity d = demand("TRIAGE");
        assertTrue(stateMachine.canTransit(d, DemandEvent.CLAIM, operator("HANDLER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.CLAIM, operator("MANAGER")));
    }

    @Test
    void canTransit_handlerOrManagerGate_submitReviewAndHold() {
        DemandEntity d = demand("ANALYZING");
        assertTrue(stateMachine.canTransit(d, DemandEvent.SUBMIT_REVIEW, operator("HANDLER")));
        assertTrue(stateMachine.canTransit(d, DemandEvent.SUBMIT_REVIEW, operator("MANAGER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.SUBMIT_REVIEW, operator("EXECUTIVE")));
        assertTrue(stateMachine.canTransit(d, DemandEvent.HOLD, operator("HANDLER")));
        assertTrue(stateMachine.canTransit(d, DemandEvent.HOLD, operator("MANAGER")));
    }

    @Test
    void canTransit_executiveOnlyGate_changeType() {
        DemandEntity d = demand("SUBMITTED");
        assertTrue(stateMachine.canTransit(d, DemandEvent.CHANGE_TYPE, operator("EXECUTIVE")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.CHANGE_TYPE, operator("MANAGER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.CHANGE_TYPE, operator("HANDLER")));
    }

    @Test
    void canTransit_anyAuthenticated_withdrawAndAcceptance() {
        DemandEntity d = demand("SUBMITTED");
        assertTrue(stateMachine.canTransit(d, DemandEvent.WITHDRAW, operator()));
        DemandEntity accepting = demand("ACCEPTANCE");
        assertTrue(stateMachine.canTransit(accepting, DemandEvent.ACCEPT_PASS, operator()));
    }

    @Test
    void canTransit_illegalEventFromState_returnsFalse() {
        DemandEntity d = demand("SUBMITTED");
        assertFalse(stateMachine.canTransit(d, DemandEvent.START, operator("HANDLER")));
    }

    @Test
    void canTransit_heldDemand_onlyResumeAllowed() {
        DemandEntity d = demand("IN_PROGRESS");
        d.setOnHold(1);
        d.setHoldSnapshotStatus("IN_PROGRESS");
        assertTrue(stateMachine.canTransit(d, DemandEvent.RESUME, operator("HANDLER")));
        assertFalse(stateMachine.canTransit(d, DemandEvent.START, operator("HANDLER")));
    }

    @Test
    void canTransit_nullOperator_returnsFalse() {
        assertFalse(stateMachine.canTransit(demand("SUBMITTED"), DemandEvent.WITHDRAW, null));
    }

    // ---------- transition：全链路 ----------

    @Test
    void transition_happyPath_appliesStatusWritesLogAndPublishesEvent() {
        DemandEntity d = demand("SUBMITTED");
        when(demandMapper.selectForUpdate(1L)).thenReturn(d);
        when(demandMapper.update(isNull(), any())).thenReturn(1);
        UserSnapshotView operatorView = new UserSnapshotView();
        operatorView.setName("王经理");
        when(userSnapshotMapper.selectById(1003L)).thenReturn(operatorView);

        DemandEntity result = stateMachine.transition(1L, DemandEvent.ACCEPT, operator("MANAGER"),
                TransitionContext.of("受理通过"));

        assertEquals("TRIAGE", result.getStatus());
        assertEquals(2, result.getVersion(), "乐观锁版本 +1");
        ArgumentCaptor<DemandTransitionLogEntity> logCaptor = ArgumentCaptor.forClass(DemandTransitionLogEntity.class);
        verify(transitionLogMapper).insert(logCaptor.capture());
        DemandTransitionLogEntity log = logCaptor.getValue();
        assertEquals("SUBMITTED", log.getFromStatus());
        assertEquals("TRIAGE", log.getToStatus());
        assertEquals("ACCEPT", log.getAction());
        assertEquals(1003L, log.getOperatorId());
        assertEquals("王经理", log.getOperatorSnapshot());
        assertEquals("受理通过", log.getComment());
        verify(eventPublisher).publishEvent(any(DemandTransitionEvent.class));
    }

    @Test
    void transition_fieldUpdaterAppliedBeforePersist() {
        DemandEntity d = demand("TRIAGE");
        when(demandMapper.selectForUpdate(1L)).thenReturn(d);
        when(demandMapper.update(isNull(), any())).thenReturn(1);

        stateMachine.transition(1L, DemandEvent.ASSIGN, operator("MANAGER"),
                TransitionContext.of("分派").withUpdater(x -> x.setAssigneeUserId(2004L)));

        assertEquals(2004L, d.getAssigneeUserId());
        assertEquals("ANALYZING", d.getStatus());
    }

    @Test
    void transition_illegalTransition_rejected1001() {
        when(demandMapper.selectForUpdate(1L)).thenReturn(demand("SUBMITTED"));

        assertBiz(() -> stateMachine.transition(1L, DemandEvent.START, operator("HANDLER"), null),
                ErrorCode.ILLEGAL_STATE_TRANSITION);
        verify(demandMapper, never()).update(any(), any());
    }

    @Test
    void transition_roleForbidden_rejected403() {
        when(demandMapper.selectForUpdate(1L)).thenReturn(demand("SUBMITTED"));

        assertBiz(() -> stateMachine.transition(1L, DemandEvent.ACCEPT, operator("HANDLER"), null),
                ErrorCode.FORBIDDEN);
        verify(demandMapper, never()).update(any(), any());
    }

    @Test
    void transition_optimisticLockConflict_rejected1003() {
        when(demandMapper.selectForUpdate(1L)).thenReturn(demand("SUBMITTED"));
        when(demandMapper.update(isNull(), any())).thenReturn(0);

        assertBiz(() -> stateMachine.transition(1L, DemandEvent.WITHDRAW, operator(), null),
                ErrorCode.CONCURRENT_CONFLICT);
    }

    @Test
    void transition_demandNotFound_rejected1002() {
        when(demandMapper.selectForUpdate(1L)).thenReturn(null);

        assertBiz(() -> stateMachine.transition(1L, DemandEvent.ACCEPT, operator("MANAGER"), null),
                ErrorCode.DEMAND_NOT_FOUND);
    }

    @Test
    void transition_nullOperator_rejected401() {
        assertBiz(() -> stateMachine.transition(1L, DemandEvent.ACCEPT, null, null),
                ErrorCode.UNAUTHORIZED);
    }

    @Test
    void transition_holdSnapshotsStatus_resumeRestores() {
        // HOLD：叠加挂起，主状态不变，快照挂起前状态
        DemandEntity d = demand("IN_PROGRESS");
        when(demandMapper.selectForUpdate(1L)).thenReturn(d);
        when(demandMapper.update(isNull(), any())).thenReturn(1);

        stateMachine.transition(1L, DemandEvent.HOLD, operator("HANDLER"), TransitionContext.of("等待外部依赖"));

        assertEquals(1, d.getOnHold());
        assertEquals("IN_PROGRESS", d.getHoldSnapshotStatus());
        assertEquals("IN_PROGRESS", d.getStatus(), "HOLD 叠加态：主状态字段不变");
        assertEquals("等待外部依赖", d.getHoldReason());
        ArgumentCaptor<DemandTransitionLogEntity> logCaptor = ArgumentCaptor.forClass(DemandTransitionLogEntity.class);
        verify(transitionLogMapper).insert(logCaptor.capture());
        assertEquals("ON_HOLD", logCaptor.getValue().getToStatus(), "挂起日志目标态记 ON_HOLD");

        // RESUME：恢复挂起前主状态
        stateMachine.transition(1L, DemandEvent.RESUME, operator("HANDLER"), null);

        assertEquals(0, d.getOnHold());
        assertNull(d.getHoldSnapshotStatus());
        assertNull(d.getHoldReason());
        assertEquals("IN_PROGRESS", d.getStatus());
    }
}

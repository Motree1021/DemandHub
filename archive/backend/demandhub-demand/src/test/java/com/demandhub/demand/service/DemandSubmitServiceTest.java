package com.demandhub.demand.service;

import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.SubmitRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 需求提交关键链路集成单测（P7 任务 7.1，FR-M2-06 + P5 任务 5.5 渠道防伪）。
 * 链路：编号生成 → 类型路由默认承接组织 → 来源渠道只信会话 claims（伪造前端传值无效）
 * → 扩展表/附件 → 状态机 DRAFT→SUBMITTED → 草稿转化。
 */
@ExtendWith(MockitoExtension.class)
class DemandSubmitServiceTest {

    @Mock
    private DemandMapper demandMapper;
    @Mock
    private DemandTypeMapper demandTypeMapper;
    @Mock
    private DemandNoGenerator demandNoGenerator;
    @Mock
    private DemandStateMachine stateMachine;
    @Mock
    private DemandExtService extService;
    @Mock
    private DraftService draftService;
    @Mock
    private AttachmentService attachmentService;
    @Mock
    private UserLookupService userLookupService;
    @InjectMocks
    private DemandSubmitService submitService;

    private CurrentUser currentUser;
    private final AtomicReference<DemandEntity> insertedRef = new AtomicReference<>();

    @BeforeEach
    void setUp() {
        currentUser = new CurrentUser();
        currentUser.setId(1006L);
        currentUser.setUserId("1006");
        currentUser.setChannel("CHUANGJIN_LS");
        UserContext.set(currentUser);
        // insert 回写自增 id（模拟 MP 主键回填），selectById 返回同一实体
        lenient().when(demandMapper.insert(any(DemandEntity.class))).thenAnswer(inv -> {
            DemandEntity d = inv.getArgument(0);
            d.setId(123L);
            insertedRef.set(d);
            return 1;
        });
        lenient().when(demandMapper.selectById(123L)).thenAnswer(inv -> insertedRef.get());
    }

    @AfterEach
    void tearDown() {
        UserContext.clear();
    }

    private static DemandTypeEntity activeTechType() {
        DemandTypeEntity t = new DemandTypeEntity();
        t.setTypeCode("TECH");
        t.setStatus("ACTIVE");
        t.setDefaultOrgId(111L);
        return t;
    }

    private void stubHappyPath() {
        when(demandTypeMapper.selectOne(any())).thenReturn(activeTechType());
        when(demandNoGenerator.next("TECH")).thenReturn("TECH-20260923-001");
        UserSnapshotView submitter = new UserSnapshotView();
        submitter.setPrimaryOrgId(900L);
        submitter.setDeptPath("外部组织");
        when(userLookupService.getById(1006L)).thenReturn(submitter);
    }

    private static BizException assertBiz(org.junit.jupiter.api.function.Executable exec, ErrorCode code) {
        BizException ex = assertThrows(BizException.class, exec);
        assertEquals(code.getCode(), ex.getCode());
        return ex;
    }

    @Test
    void submit_happyPath_fullChain() {
        stubHappyPath();
        Map<String, Object> ext = Map.of("relatedSystem", "CRM");
        SubmitRequest req = new SubmitRequest(null, "  代销看板增加持仓维度  ", "TECH", null,
                "渠道经理每天要看持仓", null, null, null, ext, List.of());

        DemandEntity result = submitService.submit(req);

        DemandEntity inserted = insertedRef.get();
        assertEquals("TECH-20260923-001", inserted.getDemandNo(), "并发安全编号生成");
        assertEquals("代销看板增加持仓维度", inserted.getTitle(), "标题 trim");
        assertEquals("DRAFT", inserted.getStatus(), "落库时 DRAFT，由状态机推进");
        assertEquals(1006L, inserted.getSubmitterId());
        assertEquals(900L, inserted.getSubmitterOrgId());
        assertEquals("NORMAL", inserted.getUrgency(), "urgency 缺省 NORMAL");
        // 类型路由：assignee_org_id = demand_type.default_org_id
        assertEquals(111L, inserted.getAssigneeOrgId());
        // 渠道防伪核心断言：来源只信会话 claims（X-Channel），与前端传值无关
        assertEquals("CHUANGJIN_LS", inserted.getChannel());

        // 链路编排：扩展表 → 附件绑定 → 状态机 DRAFT→SUBMITTED → 草稿转化
        verify(extService).writeExt(123L, "TECH", ext);
        verify(attachmentService).rebind(List.of(), "DEMAND", 123L);
        verify(stateMachine).transition(eq(123L), eq(DemandEvent.SUBMIT), eq(currentUser),
                argThat((TransitionContext ctx) -> "提交需求".equals(ctx.getComment())));
        verify(draftService).markConverted(null, 123L);
        assertEquals(123L, result.getId());
    }

    @Test
    void submit_claimsChannelMissing_defaultsToWeb() {
        currentUser.setChannel(null);
        stubHappyPath();
        SubmitRequest req = new SubmitRequest(null, "标题", "TECH", null, "内容", null,
                null, null, null, null);

        submitService.submit(req);

        assertEquals("WEB", insertedRef.get().getChannel());
    }

    @Test
    void submit_blankTitle_rejected() {
        SubmitRequest req = new SubmitRequest(null, "  ", "TECH", null, "内容", null,
                null, null, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.PARAM_INVALID);
    }

    @Test
    void submit_blankContent_rejected() {
        SubmitRequest req = new SubmitRequest(null, "标题", "TECH", null, " ", null,
                null, null, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.PARAM_INVALID);
    }

    @Test
    void submit_blankType_rejected() {
        SubmitRequest req = new SubmitRequest(null, "标题", null, null, "内容", null,
                null, null, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.PARAM_INVALID);
    }

    @Test
    void submit_inactiveType_rejected() {
        when(demandTypeMapper.selectOne(any())).thenReturn(null);
        SubmitRequest req = new SubmitRequest(null, "标题", "TECH", null, "内容", null,
                null, null, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.DEMAND_TYPE_INVALID);
    }

    @Test
    void submit_actualDemanderNotExists_rejected() {
        when(demandTypeMapper.selectOne(any())).thenReturn(activeTechType());
        when(userLookupService.exists(999L)).thenReturn(false);
        SubmitRequest req = new SubmitRequest(null, "标题", "TECH", null, "内容", null,
                null, 999L, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.USER_NOT_FOUND);
    }

    @Test
    void submit_notLoggedIn_rejected401() {
        UserContext.clear();
        SubmitRequest req = new SubmitRequest(null, "标题", "TECH", null, "内容", null,
                null, null, null, null);

        assertBiz(() -> submitService.submit(req), ErrorCode.UNAUTHORIZED);
    }

    @Test
    void withdraw_blankReason_rejected() {
        assertBiz(() -> submitService.withdraw(1L, " "), ErrorCode.PARAM_INVALID);
    }

    @Test
    void withdraw_nonSubmitter_rejected403() {
        DemandEntity demand = new DemandEntity();
        demand.setId(1L);
        demand.setSubmitterId(2000L);
        demand.setStatus("SUBMITTED");
        when(demandMapper.selectById(1L)).thenReturn(demand);

        assertBiz(() -> submitService.withdraw(1L, "填错了"), ErrorCode.FORBIDDEN);
    }

    @Test
    void withdraw_happyPath_transitionsWithCloseReason() {
        DemandEntity demand = new DemandEntity();
        demand.setId(1L);
        demand.setSubmitterId(1006L);
        demand.setStatus("SUBMITTED");
        when(demandMapper.selectById(1L)).thenReturn(demand);

        submitService.withdraw(1L, " 填错了 ");

        verify(stateMachine).transition(eq(1L), eq(DemandEvent.WITHDRAW), eq(currentUser),
                argThat((TransitionContext ctx) -> {
                    if (!"填错了".equals(ctx.getComment()) || ctx.getFieldUpdater() == null) {
                        return false;
                    }
                    // fieldUpdater 负责关闭留痕
                    DemandEntity probe = new DemandEntity();
                    ctx.getFieldUpdater().accept(probe);
                    return probe.getClosedAt() != null
                            && probe.getCloseReason() != null && probe.getCloseReason().contains("提报人撤销：填错了");
                }));
    }
}

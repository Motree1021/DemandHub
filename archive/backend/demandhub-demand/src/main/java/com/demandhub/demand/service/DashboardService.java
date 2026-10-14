package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.ManagerBoardVO;
import com.demandhub.demand.dto.OrgBoardVO;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.SlaConfigEntity;
import com.demandhub.demand.mapper.DashboardMapper;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandStatDailyMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.SlaConfigMapper;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.temporal.IsoFields;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 看板报表（FR-M6-01/02/03）：管理者看板 + 经理看板 + SLA 健康度。
 * 实时走 demand 表（与列表页同一数据范围口径，保证对账一致）；
 * demand_stat_daily 预聚合表由 StatDailyJob 每 5 分钟维护，供后续离线分析。
 */
@Service
public class DashboardService {

    private final DashboardMapper dashboardMapper;
    private final DemandMapper demandMapper;
    private final DemandTransitionLogMapper transitionLogMapper;
    private final SlaConfigMapper slaConfigMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final UserLookupService userLookupService;
    private final OrgLookupService orgLookupService;
    private final DataScopeService dataScopeService;
    private final DemandStatDailyMapper statDailyMapper;

    public DashboardService(DashboardMapper dashboardMapper, DemandMapper demandMapper,
                            DemandTransitionLogMapper transitionLogMapper, SlaConfigMapper slaConfigMapper,
                            DemandTypeMapper demandTypeMapper, UserLookupService userLookupService,
                            OrgLookupService orgLookupService, DataScopeService dataScopeService,
                            DemandStatDailyMapper statDailyMapper) {
        this.dashboardMapper = dashboardMapper;
        this.demandMapper = demandMapper;
        this.transitionLogMapper = transitionLogMapper;
        this.slaConfigMapper = slaConfigMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.userLookupService = userLookupService;
        this.orgLookupService = orgLookupService;
        this.dataScopeService = dataScopeService;
        this.statDailyMapper = statDailyMapper;
    }

    /** 时间范围解析：week 本周（周一起）/ month 本月 / quarter 本季 / custom 自定义；返回 [from, to) */
    public LocalDateTime[] resolveRange(String range, LocalDate from, LocalDate to) {
        LocalDate today = LocalDate.now();
        LocalDate start;
        if ("week".equals(range)) {
            start = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        } else if ("quarter".equals(range)) {
            int firstMonth = ((today.getMonthValue() - 1) / 3) * 3 + 1;
            start = LocalDate.of(today.getYear(), firstMonth, 1);
        } else if ("custom".equals(range) && from != null) {
            start = from;
        } else {
            // 默认本月
            start = today.withDayOfMonth(1);
        }
        LocalDate end = ("custom".equals(range) && to != null) ? to.plusDays(1) : today.plusDays(1);
        return new LocalDateTime[]{start.atStartOfDay(), end.atStartOfDay()};
    }

    /** 管理者看板（EXECUTIVE 全线 / MANAGER 授权子树，数据范围由拦截器自动注入） */
    public ManagerBoardVO managerBoard(String range, LocalDate from, LocalDate to) {
        LocalDateTime[] rt = resolveRange(range, from, to);
        LocalDateTime fromDt = rt[0];
        LocalDateTime toDt = rt[1];

        ManagerBoardVO vo = new ManagerBoardVO();
        ManagerBoardVO.Kpi kpi = new ManagerBoardVO.Kpi();
        LocalDateTime monthStart = LocalDate.now().withDayOfMonth(1).atStartOfDay();
        kpi.setMonthNew(dashboardMapper.countNewBetween(monthStart, toDt));
        kpi.setInflight(dashboardMapper.countInflight());
        kpi.setDone(dashboardMapper.countDoneBetween(fromDt, toDt));
        BigDecimal avgCycle = dashboardMapper.avgCycleHoursBetween(fromDt, toDt);
        kpi.setAvgCycleHours(avgCycle == null ? BigDecimal.ZERO : avgCycle.setScale(1, RoundingMode.HALF_UP));
        vo.setKpi(kpi);

        vo.setTrend(buildTrend());
        vo.setTypeDistribution(buildTypeDistribution(fromDt, toDt));
        vo.setChannelDistribution(buildChannelDistribution(fromDt, toDt));
        vo.setOrgBacklog(buildOrgBacklog(10));

        ManagerBoardVO.SlaHealth slaHealth = computeSlaHealth();
        vo.setSlaHealth(slaHealth);
        kpi.setSlaOver(slaHealth.getOver());
        return vo;
    }

    /** 经理看板（本承接组织维度；拦截器已按经理授权子树过滤） */
    public OrgBoardVO orgBoard() {
        OrgBoardVO vo = new OrgBoardVO();
        Map<String, Long> byStatus = dashboardMapper.countGroupByStatus().stream()
                .collect(Collectors.toMap(m -> String.valueOf(m.get("status")), m -> ((Number) m.get("cnt")).longValue(), (a, b) -> a));
        vo.setPendingAccept(byStatus.getOrDefault("SUBMITTED", 0L));
        vo.setPool(byStatus.getOrDefault("TRIAGE", 0L));
        long processing = List.of("ANALYZING", "SOLUTION_REVIEW", "CONFIRMED", "IN_PROGRESS", "ACCEPTANCE").stream()
                .mapToLong(s -> byStatus.getOrDefault(s, 0L)).sum();
        vo.setProcessing(processing);

        LocalDateTime weekStart = LocalDate.now().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).atStartOfDay();
        vo.setWeekDone(dashboardMapper.countDoneBetween(weekStart, LocalDate.now().plusDays(1).atStartOfDay()));

        List<Map<String, Object>> inflightByUser = dashboardMapper.countInflightByUser();
        Map<Long, Long> inflightMap = inflightByUser.stream()
                .collect(Collectors.toMap(m -> ((Number) m.get("userId")).longValue(),
                        m -> ((Number) m.get("inflightCnt")).longValue(), (a, b) -> a));

        // 工时：effort_log 表不被拦截器过滤，显式按当前用户数据范围限定承接组织（全类型并集）
        CurrentUser user = UserContext.get();
        DataScope scope = user == null ? DataScope.noAccess() : dataScopeService.currentScope(user);
        List<Long> orgIds = scope.isBypass() ? null : new ArrayList<>(scope.unionOrgIds());
        Map<Long, BigDecimal> effortMap = new HashMap<>();
        if (orgIds == null || !orgIds.isEmpty()) {
            effortMap = dashboardMapper.sumEffortByUser(orgIds).stream()
                    .collect(Collectors.toMap(m -> ((Number) m.get("userId")).longValue(),
                            m -> m.get("hours") == null ? BigDecimal.ZERO : new BigDecimal(m.get("hours").toString()), (a, b) -> a));
        }

        List<Long> userIds = new ArrayList<>();
        userIds.addAll(inflightMap.keySet());
        Map<Long, BigDecimal> finalEffortMap = effortMap;
        userIds.addAll(effortMap.keySet());
        Map<Long, String> names = userLookupService.namesOf(userIds.stream().distinct().collect(Collectors.toList()));

        List<OrgBoardVO.MemberWorkload> workload = userIds.stream().distinct().map(uid -> {
            OrgBoardVO.MemberWorkload w = new OrgBoardVO.MemberWorkload();
            w.setUserId(uid);
            w.setUserName(names.getOrDefault(uid, String.valueOf(uid)));
            w.setInflightCnt(inflightMap.getOrDefault(uid, 0L));
            w.setEffortHours(finalEffortMap.getOrDefault(uid, BigDecimal.ZERO).setScale(1, RoundingMode.HALF_UP));
            return w;
        }).sorted((a, b) -> Long.compare(b.getInflightCnt(), a.getInflightCnt())).collect(Collectors.toList());
        vo.setMemberWorkload(workload);

        long totalInflight = inflightMap.values().stream().mapToLong(Long::longValue).sum();
        long handlerCnt = inflightMap.values().stream().filter(c -> c > 0).count();
        vo.setAvgInflightPerHandler(handlerCnt == 0 ? BigDecimal.ZERO
                : BigDecimal.valueOf((double) totalInflight / handlerCnt).setScale(1, RoundingMode.HALF_UP));
        return vo;
    }

    /** 近 12 周趋势：周桶（周一始）升序，缺失周补 0 */
    private List<ManagerBoardVO.TrendPoint> buildTrend() {
        LocalDate thisMonday = LocalDate.now().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
        LocalDate firstMonday = thisMonday.minusWeeks(11);
        LocalDateTime from = firstMonday.atStartOfDay();
        Map<Integer, Long> newMap = toBucketMap(dashboardMapper.countNewByWeek(from));
        Map<Integer, Long> doneMap = toBucketMap(dashboardMapper.countDoneByWeek(from));

        List<ManagerBoardVO.TrendPoint> trend = new ArrayList<>();
        for (int i = 0; i < 12; i++) {
            LocalDate monday = firstMonday.plusWeeks(i);
            int bucket = isoBucket(monday);
            ManagerBoardVO.TrendPoint p = new ManagerBoardVO.TrendPoint();
            p.setWeekStart(monday.toString());
            p.setNewCnt(newMap.getOrDefault(bucket, 0L));
            p.setDoneCnt(doneMap.getOrDefault(bucket, 0L));
            trend.add(p);
        }
        return trend;
    }

    private List<ManagerBoardVO.TypeCount> buildTypeDistribution(LocalDateTime from, LocalDateTime to) {
        Map<String, String> typeNames = demandTypeMapper.selectList(null).stream()
                .collect(Collectors.toMap(DemandTypeEntity::getTypeCode, DemandTypeEntity::getTypeName, (a, b) -> a));
        return dashboardMapper.countByType(from, to).stream().map(m -> {
            ManagerBoardVO.TypeCount tc = new ManagerBoardVO.TypeCount();
            tc.setTypeCode(String.valueOf(m.get("typeCode")));
            tc.setTypeName(typeNames.getOrDefault(tc.getTypeCode(), tc.getTypeCode()));
            tc.setCnt(((Number) m.get("cnt")).longValue());
            return tc;
        }).collect(Collectors.toList());
    }

    /** 渠道来源分布：channelName 取 demand_channel 注册表（如 CHUANGJIN_LS=创金零售），未注册回退渠道码 */
    private List<ManagerBoardVO.ChannelCount> buildChannelDistribution(LocalDateTime from, LocalDateTime to) {
        Map<String, String> channelNames = dashboardMapper.listChannelNames().stream()
                .collect(Collectors.toMap(m -> String.valueOf(m.get("channelCode")),
                        m -> String.valueOf(m.get("channelName")), (a, b) -> a));
        return dashboardMapper.countByChannel(from, to).stream().map(m -> {
            ManagerBoardVO.ChannelCount cc = new ManagerBoardVO.ChannelCount();
            cc.setChannel(String.valueOf(m.get("channel")));
            cc.setChannelName(channelNames.getOrDefault(cc.getChannel(), cc.getChannel()));
            cc.setCnt(((Number) m.get("cnt")).longValue());
            return cc;
        }).collect(Collectors.toList());
    }

    private List<ManagerBoardVO.OrgBacklog> buildOrgBacklog(int limit) {
        List<Map<String, Object>> rows = dashboardMapper.topBacklogOrgs(limit);
        List<Long> orgIds = rows.stream().map(m -> ((Number) m.get("orgId")).longValue()).collect(Collectors.toList());
        Map<Long, String> orgNames = orgLookupService.namesOf(orgIds);
        return rows.stream().map(m -> {
            ManagerBoardVO.OrgBacklog ob = new ManagerBoardVO.OrgBacklog();
            ob.setOrgId(((Number) m.get("orgId")).longValue());
            ob.setOrgName(orgNames.getOrDefault(ob.getOrgId(), String.valueOf(ob.getOrgId())));
            ob.setCnt(((Number) m.get("cnt")).longValue());
            return ob;
        }).collect(Collectors.toList());
    }

    /**
     * SLA 健康度（FR-M6-03）：在途未挂起需求按 类型×状态 配置的停留阈值分档。
     * 进入当前状态时刻 = 最近一次 to_status=当前状态 的流转日志时间（兜底提交时间）；挂起期间不计（已排除挂起单）。
     */
    private ManagerBoardVO.SlaHealth computeSlaHealth() {
        ManagerBoardVO.SlaHealth health = new ManagerBoardVO.SlaHealth();
        health.setNormal(0L);
        health.setWarn(0L);
        health.setOver(0L);

        List<DemandEntity> inflight = demandMapper.selectList(new LambdaQueryWrapper<DemandEntity>()
                .select(DemandEntity::getId, DemandEntity::getDemandTypeCode, DemandEntity::getStatus,
                        DemandEntity::getSubmittedAt, DemandEntity::getCreatedAt)
                .eq(DemandEntity::getOnHold, 0)
                .notIn(DemandEntity::getStatus, "DONE", "CLOSED"));
        if (inflight.isEmpty()) {
            return health;
        }
        Map<String, SlaConfigEntity> configMap = slaConfigMapper.selectList(
                        new LambdaQueryWrapper<SlaConfigEntity>().eq(SlaConfigEntity::getEnabled, 1))
                .stream().collect(Collectors.toMap(c -> c.getDemandTypeCode() + "|" + c.getStatus(), Function.identity(), (a, b) -> a));

        List<Long> ids = inflight.stream().map(DemandEntity::getId).collect(Collectors.toList());
        // 批量取流转日志（id 倒序），Java 侧按需求分组取"进入当前状态"的最近时刻
        Map<Long, List<DemandTransitionLogEntity>> logsByDemand = transitionLogMapper.selectList(
                        new LambdaQueryWrapper<DemandTransitionLogEntity>()
                                .in(DemandTransitionLogEntity::getDemandId, ids)
                                .orderByDesc(DemandTransitionLogEntity::getId))
                .stream().collect(Collectors.groupingBy(DemandTransitionLogEntity::getDemandId));

        LocalDateTime now = LocalDateTime.now();
        for (DemandEntity d : inflight) {
            SlaConfigEntity config = configMap.get(d.getDemandTypeCode() + "|" + d.getStatus());
            if (config == null) {
                health.setNormal(health.getNormal() + 1);
                continue;
            }
            LocalDateTime enteredAt = logsByDemand.getOrDefault(d.getId(), List.of()).stream()
                    .filter(l -> Objects.equals(l.getToStatus(), d.getStatus()))
                    .findFirst()
                    .map(DemandTransitionLogEntity::getCreatedAt)
                    .orElse(d.getSubmittedAt() != null ? d.getSubmittedAt() : d.getCreatedAt());
            if (enteredAt == null) {
                health.setNormal(health.getNormal() + 1);
                continue;
            }
            long elapsedMinutes = Duration.between(enteredAt, now).toMinutes();
            if (elapsedMinutes >= config.getMaxMinutes()) {
                health.setOver(health.getOver() + 1);
            } else if (elapsedMinutes >= config.getWarnMinutes()) {
                health.setWarn(health.getWarn() + 1);
            } else {
                health.setNormal(health.getNormal() + 1);
            }
        }
        return health;
    }

    /** MySQL YEARWEEK(x,1) 对应 Java ISO 周桶：weekBasedYear * 100 + week */
    private int isoBucket(LocalDate date) {
        return date.get(IsoFields.WEEK_BASED_YEAR) * 100 + date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);
    }

    private Map<Integer, Long> toBucketMap(List<Map<String, Object>> rows) {
        return rows.stream().collect(Collectors.toMap(
                m -> ((Number) m.get("bucket")).intValue(),
                m -> ((Number) m.get("cnt")).longValue(), (a, b) -> a));
    }

    /** 手动触发预聚合（检查点 3）：立即刷新当日快照 */
    public int refreshStatDaily() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return statDailyMapper.refreshTodaySnapshot();
    }
}

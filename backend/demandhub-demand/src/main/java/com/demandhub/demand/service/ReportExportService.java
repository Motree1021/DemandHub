package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.ReportExportRequest;
import com.demandhub.demand.entity.ReportExportTaskEntity;
import com.demandhub.demand.mapper.ReportExportTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 报表导出（FR-M6-04 / 架构 4.6）：提交异步任务 → 后台生成 Excel 存 MinIO → 站内信发下载入口。
 * 数据范围在提交线程内快照（异步线程无 UserContext），保证导出口径与列表页一致。
 */
@Service
public class ReportExportService {

    private static final String NO_KEY_PREFIX = "report:no:";
    private static final Duration NO_KEY_TTL = Duration.ofHours(48);

    private final ReportExportTaskMapper taskMapper;
    private final ReportExportExecutor exportExecutor;
    private final DataScopeService dataScopeService;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ReportExportService(ReportExportTaskMapper taskMapper, ReportExportExecutor exportExecutor,
                               DataScopeService dataScopeService, StringRedisTemplate redis) {
        this.taskMapper = taskMapper;
        this.exportExecutor = exportExecutor;
        this.dataScopeService = dataScopeService;
        this.redis = redis;
    }

    /** 提交导出任务：落库 PENDING → 异步生成 */
    public ReportExportTaskEntity createTask(ReportExportRequest request) {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        // 数据范围快照（异步线程无登录上下文）
        DataScope scope = dataScopeService.currentScope(user);
        ReportExportExecutor.ExportScope scopeSnapshot = new ReportExportExecutor.ExportScope(
                scope.isBypass(), scope.isNoAccess(), List.copyOf(scope.unionOrgIds()), scope.isReporter(), user.getId());

        ReportExportTaskEntity task = new ReportExportTaskEntity();
        task.setTaskNo(nextTaskNo());
        task.setReportType(request.reportType() == null ? "DEMAND_LIST" : request.reportType());
        try {
            task.setParamsJson(objectMapper.writeValueAsString(request));
        } catch (Exception e) {
            task.setParamsJson("{}");
        }
        task.setRequesterId(user.getId());
        task.setStatus("PENDING");
        taskMapper.insert(task);

        exportExecutor.run(task.getId(), request, scopeSnapshot);
        return task;
    }

    /** 我的导出任务（倒序） */
    public List<ReportExportTaskEntity> listMine(long limit) {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return taskMapper.selectList(new LambdaQueryWrapper<ReportExportTaskEntity>()
                .eq(ReportExportTaskEntity::getRequesterId, user.getId())
                .orderByDesc(ReportExportTaskEntity::getId)
                .last("LIMIT " + Math.min(Math.max(limit, 1), 100)));
    }

    /** 下载校验：仅本人或 ADMIN/EXECUTIVE 可下载，且任务成功 */
    public ReportExportTaskEntity requireDownloadable(Long taskId) {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        ReportExportTaskEntity task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "导出任务不存在");
        }
        boolean privileged = user.hasRole("ADMIN") || user.hasRole("EXECUTIVE");
        if (!privileged && !user.getId().equals(task.getRequesterId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅任务发起人可下载");
        }
        if (!"SUCCESS".equals(task.getStatus()) || task.getFilePath() == null) {
            throw new BizException(ErrorCode.BIZ_ERROR, "报表尚未生成完成");
        }
        return task;
    }

    /** 任务编号 RPT-YYYYMMDD-NNN（Redis 原子递增，按日流水） */
    private String nextTaskNo() {
        String day = LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE);
        String key = NO_KEY_PREFIX + day;
        Long seq = redis.opsForValue().increment(key);
        if (seq == null) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "任务编号生成失败");
        }
        if (seq == 1L) {
            redis.expire(key, NO_KEY_TTL);
        }
        return String.format("RPT-%s-%03d", day, seq);
    }
}

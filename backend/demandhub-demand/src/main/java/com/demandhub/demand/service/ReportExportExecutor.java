package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.demand.dto.ReportExportRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.NotificationRowEntity;
import com.demandhub.demand.entity.ReportExportTaskEntity;
import com.demandhub.demand.entity.SysDictEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.NotificationRowMapper;
import com.demandhub.demand.mapper.ReportExportTaskMapper;
import com.demandhub.demand.mapper.SysDictMapper;
import com.demandhub.demand.statemachine.DemandStatus;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.io.ByteArrayOutputStream;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 报表导出异步执行器（FR-M6-04）：查询（带数据范围快照）→ POI 生成 Excel →
 * MinIO 存储 → 任务置 SUCCESS → 站内信通知发起人（IN_APP 直写，不阻塞）。
 */
@Slf4j
@Component
public class ReportExportExecutor {

    /** 单次导出上限，防止全量拖垮内存 */
    private static final int EXPORT_LIMIT = 5000;
    private static final DateTimeFormatter DT_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final ReportExportTaskMapper taskMapper;
    private final DemandMapper demandMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final SysDictMapper sysDictMapper;
    private final UserLookupService userLookupService;
    private final OrgLookupService orgLookupService;
    private final StorageService storageService;
    private final NotificationRowMapper notificationRowMapper;

    public ReportExportExecutor(ReportExportTaskMapper taskMapper, DemandMapper demandMapper,
                                DemandTypeMapper demandTypeMapper, SysDictMapper sysDictMapper,
                                UserLookupService userLookupService, OrgLookupService orgLookupService,
                                StorageService storageService, NotificationRowMapper notificationRowMapper) {
        this.taskMapper = taskMapper;
        this.demandMapper = demandMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.sysDictMapper = sysDictMapper;
        this.userLookupService = userLookupService;
        this.orgLookupService = orgLookupService;
        this.storageService = storageService;
        this.notificationRowMapper = notificationRowMapper;
    }

    /** 数据范围快照（提交线程内计算，异步线程无 UserContext） */
    public record ExportScope(boolean bypass, boolean noAccess, List<Long> orgIds, boolean reporter, Long userId) {
    }

    @Async
    public void run(Long taskId, ReportExportRequest request, ExportScope scope) {
        ReportExportTaskEntity task = taskMapper.selectById(taskId);
        if (task == null) {
            return;
        }
        try {
            task.setStatus("RUNNING");
            taskMapper.updateById(task);

            List<DemandEntity> rows = queryDemands(request, scope);
            byte[] excel = buildExcel(rows);

            String fileName = "需求清单_" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss")) + ".xlsx";
            String path = storageService.uploadBytes(excel, fileName,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "report");

            task.setStatus("SUCCESS");
            task.setFilePath(path);
            task.setFileName(fileName);
            task.setFinishedAt(LocalDateTime.now());
            taskMapper.updateById(task);
            notifyReady(task, rows.size());
            log.info("[ReportExport] 任务 {} 导出完成：{} 行 → {}", task.getTaskNo(), rows.size(), path);
        } catch (Exception e) {
            log.error("[ReportExport] 任务 {} 导出失败: {}", task.getTaskNo(), e.getMessage(), e);
            task.setStatus("FAILED");
            task.setErrorMsg(e.getMessage() == null ? "导出失败" : e.getMessage().substring(0, Math.min(e.getMessage().length(), 500)));
            task.setFinishedAt(LocalDateTime.now());
            taskMapper.updateById(task);
        }
    }

    /** 查询导出数据：口径与列表页一致（数据范围快照显式拼接，异步线程无拦截器上下文） */
    private List<DemandEntity> queryDemands(ReportExportRequest req, ExportScope scope) {
        LambdaQueryWrapper<DemandEntity> wrapper = new LambdaQueryWrapper<DemandEntity>()
                .eq(StringUtils.hasText(req.status()), DemandEntity::getStatus, req.status())
                .eq(StringUtils.hasText(req.demandTypeCode()), DemandEntity::getDemandTypeCode, req.demandTypeCode())
                .eq(StringUtils.hasText(req.urgency()), DemandEntity::getUrgency, req.urgency())
                .and(StringUtils.hasText(req.keyword()), w -> w.like(DemandEntity::getTitle, req.keyword())
                        .or().like(DemandEntity::getDemandNo, req.keyword()))
                .ge(req.submittedFrom() != null, DemandEntity::getSubmittedAt,
                        req.submittedFrom() == null ? null : req.submittedFrom().atStartOfDay())
                .lt(req.submittedTo() != null, DemandEntity::getSubmittedAt,
                        req.submittedTo() == null ? null : req.submittedTo().plusDays(1).atStartOfDay())
                .and(Boolean.TRUE.equals(req.mine()), w -> w.eq(DemandEntity::getSubmitterId, scope.userId())
                        .or().eq(DemandEntity::getActualDemanderId, scope.userId()));
        if (scope.noAccess()) {
            wrapper.apply("1 = 0");
        } else if (!scope.bypass()) {
            wrapper.and(w -> {
                boolean has = false;
                if (!scope.orgIds().isEmpty()) {
                    w.in(DemandEntity::getAssigneeOrgId, scope.orgIds());
                    has = true;
                }
                if (scope.reporter()) {
                    if (has) {
                        w.or();
                    }
                    w.eq(DemandEntity::getSubmitterId, scope.userId());
                    has = true;
                }
                if (!has) {
                    w.apply("1 = 0");
                }
            });
        }
        wrapper.orderByDesc(DemandEntity::getId).last("LIMIT " + EXPORT_LIMIT);
        return demandMapper.selectList(wrapper);
    }

    private byte[] buildExcel(List<DemandEntity> rows) throws Exception {
        Set<Long> userIds = new HashSet<>();
        Set<Long> orgIds = new HashSet<>();
        rows.forEach(d -> {
            userIds.add(d.getSubmitterId());
            if (d.getAssigneeUserId() != null) {
                userIds.add(d.getAssigneeUserId());
            }
            if (d.getAssigneeOrgId() != null) {
                orgIds.add(d.getAssigneeOrgId());
            }
            if (d.getSubmitterOrgId() != null) {
                orgIds.add(d.getSubmitterOrgId());
            }
        });
        Map<Long, String> userNames = userLookupService.namesOf(userIds);
        Map<Long, String> orgNames = orgLookupService.namesOf(orgIds);
        Map<String, String> typeNames = demandTypeMapper.selectList(null).stream()
                .collect(Collectors.toMap(DemandTypeEntity::getTypeCode, DemandTypeEntity::getTypeName, (a, b) -> a));
        Map<String, String> urgencyNames = sysDictMapper.selectList(
                        new LambdaQueryWrapper<SysDictEntity>().eq(SysDictEntity::getDictType, "URGENCY"))
                .stream().collect(Collectors.toMap(SysDictEntity::getItemCode, SysDictEntity::getItemName, (a, b) -> a));

        String[] headers = {"需求编号", "标题", "类型", "状态", "紧急程度", "提报人", "提报组织", "承接组织", "处理人",
                "提交时间", "期望交付", "关闭时间", "交付周期(小时)"};
        try (Workbook workbook = new XSSFWorkbook(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            Sheet sheet = workbook.createSheet("需求清单");
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);

            Row header = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++) {
                header.createCell(i).setCellValue(headers[i]);
                header.getCell(i).setCellStyle(headerStyle);
            }
            int r = 1;
            for (DemandEntity d : rows) {
                Row row = sheet.createRow(r++);
                int c = 0;
                row.createCell(c++).setCellValue(nullToEmpty(d.getDemandNo()));
                row.createCell(c++).setCellValue(nullToEmpty(d.getTitle()));
                row.createCell(c++).setCellValue(typeNames.getOrDefault(d.getDemandTypeCode(), nullToEmpty(d.getDemandTypeCode())));
                row.createCell(c++).setCellValue(statusLabel(d.getStatus()));
                row.createCell(c++).setCellValue(urgencyNames.getOrDefault(d.getUrgency(), nullToEmpty(d.getUrgency())));
                row.createCell(c++).setCellValue(userNames.getOrDefault(d.getSubmitterId(), String.valueOf(d.getSubmitterId())));
                row.createCell(c++).setCellValue(d.getSubmitterOrgId() == null ? "" : orgNames.getOrDefault(d.getSubmitterOrgId(), String.valueOf(d.getSubmitterOrgId())));
                row.createCell(c++).setCellValue(d.getAssigneeOrgId() == null ? "" : orgNames.getOrDefault(d.getAssigneeOrgId(), String.valueOf(d.getAssigneeOrgId())));
                row.createCell(c++).setCellValue(d.getAssigneeUserId() == null ? "" : userNames.getOrDefault(d.getAssigneeUserId(), String.valueOf(d.getAssigneeUserId())));
                row.createCell(c++).setCellValue(d.getSubmittedAt() == null ? "" : DT_FMT.format(d.getSubmittedAt()));
                row.createCell(c++).setCellValue(d.getExpectDeliveryAt() == null ? "" : DT_FMT.format(d.getExpectDeliveryAt()));
                row.createCell(c++).setCellValue(d.getClosedAt() == null ? "" : DT_FMT.format(d.getClosedAt()));
                row.createCell(c).setCellValue(cycleHours(d));
            }
            for (int i = 0; i < headers.length; i++) {
                sheet.setColumnWidth(i, 16 * 256);
            }
            workbook.write(out);
            return out.toByteArray();
        }
    }

    private void notifyReady(ReportExportTaskEntity task, int rowCount) {
        try {
            NotificationRowEntity notice = new NotificationRowEntity();
            notice.setDemandId(null);
            notice.setReceiverId(task.getRequesterId());
            notice.setChannel("IN_APP");
            notice.setTemplateCode("REPORT_READY");
            notice.setTitle("报表已就绪：需求清单");
            notice.setContent("您导出的报表「需求清单」（" + rowCount + " 行）已生成，点击本通知前往下载。");
            notice.setLink("/board?tab=tasks");
            notice.setIsRead(0);
            notice.setSendStatus("SENT");
            notice.setRetryCount(0);
            notice.setSentAt(LocalDateTime.now());
            notificationRowMapper.insert(notice);
        } catch (Exception e) {
            // 通知失败不回滚导出结果
            log.error("[ReportExport] 就绪通知发送失败: {}", e.getMessage());
        }
    }

    private String statusLabel(String status) {
        try {
            return DemandStatus.valueOf(status).getLabel();
        } catch (Exception e) {
            return nullToEmpty(status);
        }
    }

    private String cycleHours(DemandEntity d) {
        if (d.getSubmittedAt() == null || d.getClosedAt() == null) {
            return "";
        }
        long minutes = ChronoUnit.MINUTES.between(d.getSubmittedAt(), d.getClosedAt());
        return String.format("%.1f", minutes / 60.0);
    }

    private String nullToEmpty(String v) {
        return v == null ? "" : v;
    }
}

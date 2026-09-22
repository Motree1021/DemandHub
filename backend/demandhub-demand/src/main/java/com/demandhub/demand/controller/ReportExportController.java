package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.ReportExportRequest;
import com.demandhub.demand.entity.ReportExportTaskEntity;
import com.demandhub.demand.service.ReportExportService;
import com.demandhub.demand.service.StorageService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * 报表导出（M6，FR-M6-04）：异步任务 → Excel 存 MinIO → 站内信通知 → 下载。
 */
@Tag(name = "报表导出")
@RestController
@RequestMapping("/demand/report")
public class ReportExportController {

    private final ReportExportService reportExportService;
    private final StorageService storageService;

    public ReportExportController(ReportExportService reportExportService, StorageService storageService) {
        this.reportExportService = reportExportService;
        this.storageService = storageService;
    }

    @Operation(summary = "创建导出任务（异步，完成后站内信通知）")
    @PostMapping("/export")
    @RequireRole({"EXECUTIVE", "MANAGER", "ADMIN"})
    public Result<ReportExportTaskEntity> export(@RequestBody ReportExportRequest request) {
        return Result.ok(reportExportService.createTask(request));
    }

    @Operation(summary = "我的导出任务列表")
    @GetMapping("/tasks")
    public Result<List<ReportExportTaskEntity>> myTasks(@RequestParam(defaultValue = "20") long limit) {
        return Result.ok(reportExportService.listMine(limit));
    }

    @Operation(summary = "下载导出文件（仅本人或 ADMIN/EXECUTIVE）")
    @GetMapping("/download/{taskId}")
    public void download(@PathVariable Long taskId, HttpServletResponse response) throws Exception {
        ReportExportTaskEntity task = reportExportService.requireDownloadable(taskId);
        String fileName = task.getFileName() == null ? "report.xlsx" : task.getFileName();
        response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''"
                + URLEncoder.encode(fileName, StandardCharsets.UTF_8));
        try (InputStream in = storageService.download(task.getFilePath());
             OutputStream out = response.getOutputStream()) {
            in.transferTo(out);
            out.flush();
        }
    }
}

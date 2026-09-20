package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.AttachmentEntity;
import com.demandhub.demand.service.AttachmentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * 附件（FR-M2-04）：上传（≤50MB，单需求 ≤20 个）/下载/删除/按业务列表。
 */
@Tag(name = "附件")
@RestController
@RequestMapping("/demand/attachment")
public class AttachmentController {

    private final AttachmentService attachmentService;

    public AttachmentController(AttachmentService attachmentService) {
        this.attachmentService = attachmentService;
    }

    @Operation(summary = "上传附件（bizType: DRAFT/DEMAND/SOLUTION/COMMENT）")
    @PostMapping("/upload")
    public Result<AttachmentEntity> upload(@RequestParam String bizType,
                                           @RequestParam Long bizId,
                                           @RequestParam("file") MultipartFile file) {
        return Result.ok(attachmentService.upload(bizType, bizId, file));
    }

    @Operation(summary = "按业务对象列出附件")
    @GetMapping("/list")
    public Result<List<AttachmentEntity>> list(@RequestParam String bizType, @RequestParam Long bizId) {
        return Result.ok(attachmentService.listByBiz(bizType, bizId));
    }

    @Operation(summary = "下载附件")
    @GetMapping("/{id}/download")
    public void download(@PathVariable Long id, HttpServletResponse response) throws Exception {
        AttachmentEntity attachment = attachmentService.getForDownload(id);
        response.setContentType(attachment.getMimeType() == null
                ? MediaType.APPLICATION_OCTET_STREAM_VALUE : attachment.getMimeType());
        String encoded = URLEncoder.encode(attachment.getFileName(), StandardCharsets.UTF_8).replace("+", "%20");
        response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + encoded);
        response.setContentLengthLong(attachment.getFileSize());
        try (InputStream in = attachmentService.download(attachment);
             OutputStream out = response.getOutputStream()) {
            in.transferTo(out);
            out.flush();
        }
    }

    @Operation(summary = "删除附件（仅上传人，已完成需求不可删）")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        attachmentService.delete(id);
        return Result.ok();
    }
}

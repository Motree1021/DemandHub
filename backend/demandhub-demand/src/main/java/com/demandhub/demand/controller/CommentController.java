package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.CommentAddRequest;
import com.demandhub.demand.dto.CommentUpdateRequest;
import com.demandhub.demand.entity.CommentEntity;
import com.demandhub.demand.service.CommentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * M4 评论沟通：文字 + 附件 + @人；评论不可删除，仅作者可追加补充（FR-M4-07）。
 */
@Tag(name = "需求评论")
@RestController
@RequestMapping("/demand/comment")
public class CommentController {

    private final CommentService commentService;

    public CommentController(CommentService commentService) {
        this.commentService = commentService;
    }

    @Operation(summary = "发表评论（支持 @人与附件）")
    @PostMapping
    public Result<CommentEntity> add(@RequestBody CommentAddRequest request) {
        return Result.ok(commentService.add(request));
    }

    @Operation(summary = "追加补充（仅作者本人）")
    @PutMapping("/{id}")
    public Result<CommentEntity> update(@PathVariable Long id, @RequestBody CommentUpdateRequest request) {
        return Result.ok(commentService.update(id, request));
    }

    @Operation(summary = "评论时间线")
    @GetMapping("/list")
    public Result<List<CommentEntity>> list(@RequestParam Long demandId) {
        return Result.ok(commentService.listByDemand(demandId));
    }
}

package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.AttachmentEntity;
import com.demandhub.demand.entity.CommentEntity;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.SolutionEntity;
import com.demandhub.demand.mapper.AttachmentMapper;
import com.demandhub.demand.mapper.CommentMapper;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.SolutionMapper;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.util.List;
import java.util.Set;

/**
 * 附件服务（FR-M2-04）：上传/下载/删除/业务绑定，元数据写 attachment 表。
 * 限制：单文件 ≤ 50MB，单需求 ≤ 20 个附件。
 */
@Service
public class AttachmentService {

    private static final long MAX_FILE_SIZE = 50L * 1024 * 1024;
    private static final int MAX_PER_DEMAND = 20;
    private static final Set<String> BIZ_TYPES = Set.of("DEMAND", "SOLUTION", "COMMENT", "DRAFT");

    private final AttachmentMapper attachmentMapper;
    private final StorageService storageService;
    private final DemandMapper demandMapper;
    private final SolutionMapper solutionMapper;
    private final CommentMapper commentMapper;

    public AttachmentService(AttachmentMapper attachmentMapper, StorageService storageService,
                             DemandMapper demandMapper, SolutionMapper solutionMapper,
                             CommentMapper commentMapper) {
        this.attachmentMapper = attachmentMapper;
        this.storageService = storageService;
        this.demandMapper = demandMapper;
        this.solutionMapper = solutionMapper;
        this.commentMapper = commentMapper;
    }

    public AttachmentEntity upload(String bizType, Long bizId, MultipartFile file) {
        if (!BIZ_TYPES.contains(bizType)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "不支持的附件业务类型: " + bizType);
        }
        if (file == null || file.isEmpty()) {
            throw new BizException(ErrorCode.PARAM_INVALID, "文件不能为空");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new BizException(ErrorCode.FILE_TOO_LARGE, "单文件不能超过 50MB");
        }
        if ("DEMAND".equals(bizType)) {
            requireVisibleDemand(bizId);
            Long count = attachmentMapper.selectCount(new LambdaQueryWrapper<AttachmentEntity>()
                    .eq(AttachmentEntity::getBizType, "DEMAND").eq(AttachmentEntity::getBizId, bizId));
            if (count >= MAX_PER_DEMAND) {
                throw new BizException(ErrorCode.ATTACHMENT_LIMIT, "单需求附件不能超过 " + MAX_PER_DEMAND + " 个");
            }
        }
        String path = storageService.upload(file, bizType);
        AttachmentEntity entity = new AttachmentEntity();
        entity.setBizType(bizType);
        entity.setBizId(bizId);
        String original = file.getOriginalFilename() == null ? "file" : file.getOriginalFilename();
        entity.setFileName(original);
        entity.setFilePath(path);
        entity.setFileSize(file.getSize());
        entity.setMimeType(file.getContentType());
        int dot = original.lastIndexOf('.');
        if (dot >= 0 && dot < original.length() - 1) {
            entity.setExt(original.substring(dot + 1).toLowerCase());
        }
        entity.setUploadedBy(UserContext.currentUserId());
        attachmentMapper.insert(entity);
        return entity;
    }

    public List<AttachmentEntity> listByBiz(String bizType, Long bizId) {
        return attachmentMapper.selectList(new LambdaQueryWrapper<AttachmentEntity>()
                .eq(AttachmentEntity::getBizType, bizType)
                .eq(AttachmentEntity::getBizId, bizId)
                .orderByAsc(AttachmentEntity::getId));
    }

    /**
     * 提交/评论时把暂存附件（DRAFT 业务）绑定到正式业务对象；仅允许绑定本人上传的附件。
     */
    public void rebind(List<Long> attachmentIds, String bizType, Long bizId) {
        if (attachmentIds == null || attachmentIds.isEmpty()) {
            return;
        }
        Long currentUserId = UserContext.currentUserId();
        for (Long id : attachmentIds) {
            AttachmentEntity attachment = attachmentMapper.selectById(id);
            if (attachment == null) {
                throw new BizException(ErrorCode.ATTACHMENT_NOT_FOUND, "附件不存在: " + id);
            }
            if (!currentUserId.equals(attachment.getUploadedBy())) {
                throw new BizException(ErrorCode.FORBIDDEN, "只能绑定本人上传的附件");
            }
            attachment.setBizType(bizType);
            attachment.setBizId(bizId);
            attachmentMapper.updateById(attachment);
        }
    }

    /** 下载前鉴权：返回附件实体，无权访问抛 403 */
    public AttachmentEntity getForDownload(Long id) {
        AttachmentEntity attachment = attachmentMapper.selectById(id);
        if (attachment == null) {
            throw new BizException(ErrorCode.ATTACHMENT_NOT_FOUND);
        }
        switch (attachment.getBizType()) {
            case "DRAFT" -> {
                if (!UserContext.currentUserId().equals(attachment.getUploadedBy())) {
                    throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该附件");
                }
            }
            case "DEMAND" -> requireVisibleDemand(attachment.getBizId());
            case "SOLUTION" -> {
                SolutionEntity solution = solutionMapper.selectById(attachment.getBizId());
                if (solution == null) {
                    throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该附件");
                }
                requireVisibleDemand(solution.getDemandId());
            }
            case "COMMENT" -> {
                CommentEntity comment = commentMapper.selectById(attachment.getBizId());
                if (comment == null) {
                    throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该附件");
                }
                requireVisibleDemand(comment.getDemandId());
            }
            default -> throw new BizException(ErrorCode.FORBIDDEN, "无权限访问该附件");
        }
        return attachment;
    }

    public InputStream download(AttachmentEntity attachment) {
        return storageService.download(attachment.getFilePath());
    }

    /** 删除：仅上传人本人或 ADMIN；需求完成后不可删 */
    public void delete(Long id) {
        AttachmentEntity attachment = attachmentMapper.selectById(id);
        if (attachment == null) {
            throw new BizException(ErrorCode.ATTACHMENT_NOT_FOUND);
        }
        boolean owner = UserContext.currentUserId().equals(attachment.getUploadedBy());
        if (!owner && !UserContext.hasRole("ADMIN")) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅上传人可删除附件");
        }
        if ("DEMAND".equals(attachment.getBizType())) {
            DemandEntity demand = demandMapper.selectById(attachment.getBizId());
            if (demand != null && "DONE".equals(demand.getStatus())) {
                throw new BizException(ErrorCode.BIZ_ERROR, "需求已完成，附件不可删除");
            }
        }
        attachmentMapper.deleteById(id);
        storageService.remove(attachment.getFilePath());
    }

    /** 需求必须存在且当前用户可见（数据权限拦截器对 SELECT 生效） */
    private void requireVisibleDemand(Long demandId) {
        DemandEntity demand = demandMapper.selectById(demandId);
        if (demand == null) {
            throw new BizException(ErrorCode.FORBIDDEN, "需求不存在或无权限访问");
        }
    }
}

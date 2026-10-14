package com.demandhub.demand.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.config.MinioConfig;
import io.minio.GetObjectArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

/**
 * 对象存储服务（MinIO）：文件读写，路径 {bizType}/{yyyyMM}/{uuid}.{ext}
 */
@Service
public class StorageService {

    private final MinioClient minioClient;
    private final MinioConfig minioConfig;

    public StorageService(MinioClient minioClient, MinioConfig minioConfig) {
        this.minioClient = minioClient;
        this.minioConfig = minioConfig;
    }

    public String upload(MultipartFile file, String bizType) {
        String original = file.getOriginalFilename() == null ? "file" : file.getOriginalFilename();
        String ext = "";
        int dot = original.lastIndexOf('.');
        if (dot >= 0 && dot < original.length() - 1) {
            ext = "." + original.substring(dot + 1).toLowerCase();
        }
        String path = bizType.toLowerCase() + "/"
                + LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMM")) + "/"
                + UUID.randomUUID().toString().replace("-", "") + ext;
        try (InputStream in = file.getInputStream()) {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(minioConfig.getBucket())
                    .object(path)
                    .stream(in, file.getSize(), -1)
                    .contentType(file.getContentType() == null ? "application/octet-stream" : file.getContentType())
                    .build());
            return path;
        } catch (Exception e) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "文件上传失败: " + e.getMessage());
        }
    }

    /**
     * 字节流上传（报表导出等后台生成文件）：路径 {bizType}/{yyyyMM}/{uuid}.{ext}
     */
    public String uploadBytes(byte[] data, String fileName, String contentType, String bizType) {
        String ext = "";
        int dot = fileName == null ? -1 : fileName.lastIndexOf('.');
        if (dot >= 0 && dot < fileName.length() - 1) {
            ext = "." + fileName.substring(dot + 1).toLowerCase();
        }
        String path = bizType.toLowerCase() + "/"
                + LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMM")) + "/"
                + UUID.randomUUID().toString().replace("-", "") + ext;
        try (InputStream in = new java.io.ByteArrayInputStream(data)) {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(minioConfig.getBucket())
                    .object(path)
                    .stream(in, data.length, -1)
                    .contentType(contentType == null ? "application/octet-stream" : contentType)
                    .build());
            return path;
        } catch (Exception e) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "文件上传失败: " + e.getMessage());
        }
    }

    public InputStream download(String path) {
        try {
            return minioClient.getObject(GetObjectArgs.builder()
                    .bucket(minioConfig.getBucket())
                    .object(path)
                    .build());
        } catch (Exception e) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "文件下载失败: " + e.getMessage());
        }
    }

    public void remove(String path) {
        try {
            minioClient.removeObject(RemoveObjectArgs.builder()
                    .bucket(minioConfig.getBucket())
                    .object(path)
                    .build());
        } catch (Exception ignored) {
            // 对象删除失败不阻断业务（元数据已删）
        }
    }
}

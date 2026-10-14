package com.demandhub.demand.config;

import io.minio.BucketExistsArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MinIO 对象存储配置：附件文件存 bucket，attachment 表存元数据。
 */
@Slf4j
@Data
@Configuration
@ConfigurationProperties(prefix = "demandhub.minio")
public class MinioConfig {

    private String endpoint;

    private String accessKey;

    private String secretKey;

    private String bucket;

    @Bean
    public MinioClient minioClient() {
        MinioClient client = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
        try {
            boolean exists = client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!exists) {
                client.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
                log.info("MinIO bucket [{}] 已创建", bucket);
            }
        } catch (Exception e) {
            // 启动时 MinIO 未就绪不阻断服务，上传时再报错
            log.warn("MinIO bucket 检查失败（上传功能暂不可用）: {}", e.getMessage());
        }
        return client;
    }
}

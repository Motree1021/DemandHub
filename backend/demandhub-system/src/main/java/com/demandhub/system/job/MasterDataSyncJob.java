package com.demandhub.system.job;

import com.demandhub.system.service.MasterDataSyncService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 主数据同步定时任务（FR-M1-02）：全量每日凌晨一次，增量每 5 分钟一次（带增量水印）。
 */
@Slf4j
@Component
public class MasterDataSyncJob {

    private final MasterDataSyncService syncService;

    public MasterDataSyncJob(MasterDataSyncService syncService) {
        this.syncService = syncService;
    }

    /**
     * 全量同步：每日 02:00
     */
    @Scheduled(cron = "0 0 2 * * ?")
    public void fullSync() {
        try {
            syncService.fullSync();
        } catch (Exception e) {
            log.error("主数据全量同步失败: {}", e.getMessage(), e);
        }
    }

    /**
     * 增量同步：每 5 分钟
     */
    @Scheduled(fixedDelayString = "PT5M", initialDelayString = "PT1M")
    public void incrementalSync() {
        try {
            syncService.incrementalSync();
        } catch (Exception e) {
            log.error("主数据增量同步失败: {}", e.getMessage(), e);
        }
    }
}

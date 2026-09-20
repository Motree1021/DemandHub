package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.integration.pcenter.PermissionCenterClient;
import com.demandhub.system.integration.pcenter.dto.MasterDataChanges;
import com.demandhub.system.integration.pcenter.dto.PcOrg;
import com.demandhub.system.integration.pcenter.dto.PcUser;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 主数据只读镜像同步（FR-M1-02 / IR-08）：
 * 全量每日凌晨一次，增量每 5 分钟一次（Redis 存增量水印）；
 * 权限中心不可用时本地镜像降级鉴权（登录流程自动降级）。
 */
@Slf4j
@Service
public class MasterDataSyncService {

    private static final String WATERMARK_KEY = "sync:watermark";

    private final PermissionCenterClient pcenterClient;
    private final UserSnapshotMapper userMapper;
    private final OrgSnapshotMapper orgMapper;
    private final StringRedisTemplate redis;

    public MasterDataSyncService(PermissionCenterClient pcenterClient,
                                 UserSnapshotMapper userMapper,
                                 OrgSnapshotMapper orgMapper,
                                 StringRedisTemplate redis) {
        this.pcenterClient = pcenterClient;
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
        this.redis = redis;
    }

    /**
     * 全量同步：以权限中心当前状态为准 upsert 全部用户与组织
     */
    @Transactional
    public SyncResult fullSync() {
        List<PcOrg> orgs = pcenterClient.listAllOrgs();
        List<PcUser> users = pcenterClient.listAllUsers();
        orgs.forEach(this::upsertOrg);
        users.forEach(this::upsertUser);
        saveWatermark(LocalDateTime.now());
        log.info("主数据全量同步完成: orgs={}, users={}", orgs.size(), users.size());
        return new SyncResult(orgs.size(), users.size());
    }

    /**
     * 增量同步：拉取水印之后的变更；首次无水印时退化为全量
     */
    @Transactional
    public SyncResult incrementalSync() {
        LocalDateTime watermark = loadWatermark();
        if (watermark == null) {
            log.info("无增量水印，执行首次全量同步");
            return fullSync();
        }
        MasterDataChanges changes = pcenterClient.listChanges(watermark);
        if (changes.isEmpty()) {
            saveWatermark(LocalDateTime.now());
            return new SyncResult(0, 0);
        }
        changes.getOrgs().forEach(this::upsertOrg);
        changes.getUsers().forEach(this::upsertUser);
        saveWatermark(LocalDateTime.now());
        log.info("主数据增量同步完成: orgs={}, users={}", changes.getOrgs().size(), changes.getUsers().size());
        return new SyncResult(changes.getOrgs().size(), changes.getUsers().size());
    }

    /**
     * 用户镜像 upsert（登录自动建档也走这里）
     */
    public UserSnapshot upsertUser(PcUser pc) {
        UserSnapshot snapshot = userMapper.selectOne(
                new LambdaQueryWrapper<UserSnapshot>().eq(UserSnapshot::getUserId, pc.getUserId()));
        LocalDateTime now = LocalDateTime.now();
        if (snapshot == null) {
            snapshot = new UserSnapshot();
            snapshot.setId(pc.getId());
            snapshot.setUserId(pc.getUserId());
            snapshot.setCreatedAt(now);
            fillUser(snapshot, pc, now);
            userMapper.insert(snapshot);
        } else {
            fillUser(snapshot, pc, now);
            userMapper.updateById(snapshot);
        }
        return snapshot;
    }

    private void fillUser(UserSnapshot snapshot, PcUser pc, LocalDateTime now) {
        snapshot.setName(pc.getName());
        snapshot.setWecomId(pc.getWecomId());
        snapshot.setEmployeeNo(pc.getEmployeeNo());
        snapshot.setPrimaryOrgId(pc.getPrimaryOrgId());
        snapshot.setDeptPath(pc.getDeptPath());
        snapshot.setPhone(pc.getPhone());
        snapshot.setEmail(pc.getEmail());
        snapshot.setStatus(pc.getStatus());
        snapshot.setSyncedAt(now);
        snapshot.setUpdatedAt(now);
    }

    /**
     * 组织镜像 upsert
     */
    public OrgSnapshot upsertOrg(PcOrg pc) {
        OrgSnapshot snapshot = orgMapper.selectOne(
                new LambdaQueryWrapper<OrgSnapshot>().eq(OrgSnapshot::getOrgId, pc.getOrgId()));
        LocalDateTime now = LocalDateTime.now();
        if (snapshot == null) {
            snapshot = new OrgSnapshot();
            snapshot.setId(pc.getOrgId());
            snapshot.setOrgId(pc.getOrgId());
            snapshot.setCreatedAt(now);
            fillOrg(snapshot, pc, now);
            orgMapper.insert(snapshot);
        } else {
            fillOrg(snapshot, pc, now);
            orgMapper.updateById(snapshot);
        }
        return snapshot;
    }

    private void fillOrg(OrgSnapshot snapshot, PcOrg pc, LocalDateTime now) {
        snapshot.setName(pc.getName());
        snapshot.setLevel(pc.getLevel());
        snapshot.setParentId(pc.getParentId());
        snapshot.setPath(pc.getPath());
        snapshot.setOrgKind(pc.getOrgKind());
        snapshot.setStatus(pc.getStatus());
        snapshot.setSyncedAt(now);
        snapshot.setUpdatedAt(now);
    }

    private LocalDateTime loadWatermark() {
        String v = redis.opsForValue().get(WATERMARK_KEY);
        return v == null ? null : LocalDateTime.parse(v);
    }

    private void saveWatermark(LocalDateTime watermark) {
        redis.opsForValue().set(WATERMARK_KEY, watermark.toString());
    }

    /**
     * 同步结果（org 数 / user 数）
     */
    public record SyncResult(int orgCount, int userCount) {
    }
}

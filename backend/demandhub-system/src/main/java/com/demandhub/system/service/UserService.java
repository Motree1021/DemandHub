package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * OneID 用户服务（demand_user CRUD 基础，FR-M1-01）。
 * 集中用户查询/建号/登录信息更新/密码维护，供认证、渠道匹配引擎、用户合并共用。
 * 管理端分页/补全/停用等接口在 P4 扩展。
 */
@Service
public class UserService {

    /** 外部虚拟组织：渠道部门未映射时的兜底挂载点（不阻塞登录提报，回流校准清单） */
    public static final long EXTERNAL_ORG_ID = 900L;

    private final UserSnapshotMapper userMapper;
    private final OrgSnapshotMapper orgMapper;

    public UserService(UserSnapshotMapper userMapper, OrgSnapshotMapper orgMapper) {
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
    }

    public UserSnapshot findById(Long id) {
        return id == null ? null : userMapper.selectById(id);
    }

    public UserSnapshot findByPhone(String phone) {
        if (phone == null || phone.isBlank()) {
            return null;
        }
        return userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>().eq(UserSnapshot::getPhone, phone));
    }

    public UserSnapshot findByWecomUserid(String wecomUserid) {
        if (wecomUserid == null || wecomUserid.isBlank()) {
            return null;
        }
        return userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>().eq(UserSnapshot::getWecomId, wecomUserid));
    }

    public UserSnapshot findByLoginName(String loginName) {
        if (loginName == null || loginName.isBlank()) {
            return null;
        }
        return userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>().eq(UserSnapshot::getLoginName, loginName));
    }

    /**
     * 渠道自动建号（D4：票据校验通过且带回企微 userid 即认定在职员工，ACTIVE + is_employee=1；
     * 无手机且无 userid 的字段缺失票据只兜 PENDING）。
     */
    public UserSnapshot createChannelUser(String name, String phone, String wecomUserid,
                                          Long primaryOrgId, boolean active) {
        UserSnapshot user = new UserSnapshot();
        user.setName(name);
        user.setPhone(phone);
        user.setWecomId(wecomUserid);
        user.setIsEmployee(active ? 1 : 0);
        user.setPrimaryOrgId(primaryOrgId != null ? primaryOrgId : EXTERNAL_ORG_ID);
        user.setStatus(active ? "ACTIVE" : "PENDING");
        userMapper.insert(user);
        return user;
    }

    /** 更新最后登录渠道/时间 */
    public void touchLastLogin(Long userId, String channelCode) {
        UserSnapshot update = new UserSnapshot();
        update.setId(userId);
        update.setLastLoginChannel(channelCode);
        update.setLastLoginAt(LocalDateTime.now());
        userMapper.updateById(update);
    }

    /** 设置/重置密码（BCrypt 哈希由调用方生成），并刷新 password_updated_at */
    public void updatePassword(Long userId, String passwordHash) {
        UserSnapshot update = new UserSnapshot();
        update.setId(userId);
        update.setPasswordHash(passwordHash);
        update.setPasswordUpdatedAt(LocalDateTime.now());
        userMapper.updateById(update);
    }

    /** 合并后置 MERGED 并指向目标 OneID */
    public void markMerged(Long sourceUserId, Long targetUserId) {
        UserSnapshot update = new UserSnapshot();
        update.setId(sourceUserId);
        update.setStatus("MERGED");
        update.setMergedToUserId(targetUserId);
        // 释放唯一键占用（login_name/phone/wecom_userid），避免与目标账号冲突
        update.setLoginName(null);
        update.setPhone(null);
        update.setWecomId(null);
        userMapper.updateById(update);
    }

    public List<UserSnapshot> listActiveUsers() {
        return userMapper.selectList(new LambdaQueryWrapper<UserSnapshot>()
                .eq(UserSnapshot::getStatus, "ACTIVE")
                .orderByAsc(UserSnapshot::getId));
    }

    public OrgSnapshot findOrgByExternalDeptId(String externalDeptId) {
        if (externalDeptId == null || externalDeptId.isBlank()) {
            return null;
        }
        return orgMapper.selectOne(new LambdaQueryWrapper<OrgSnapshot>()
                .eq(OrgSnapshot::getExternalDeptId, externalDeptId));
    }

    /** 部门名称路径由组织树物化 path 派生（如 创金合信零售业务线/财管科技产品部） */
    public String buildDeptPath(Long orgId) {
        if (orgId == null) {
            return null;
        }
        OrgSnapshot org = orgMapper.selectById(orgId);
        if (org == null || org.getPath() == null) {
            return null;
        }
        String[] ids = org.getPath().split("/");
        StringBuilder sb = new StringBuilder();
        for (String id : ids) {
            if (id.isBlank()) {
                continue;
            }
            OrgSnapshot node = orgMapper.selectById(Long.parseLong(id));
            if (node != null) {
                if (sb.length() > 0) {
                    sb.append("/");
                }
                sb.append(node.getName());
            }
        }
        return sb.length() == 0 ? null : sb.toString();
    }
}

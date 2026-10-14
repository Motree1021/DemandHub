package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

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
    private final SessionService sessionService;

    public UserService(UserSnapshotMapper userMapper, OrgSnapshotMapper orgMapper, SessionService sessionService) {
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
        this.sessionService = sessionService;
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

    // ==================== P4 管理端操作（仅 ADMIN，见 UserController） ====================

    /** 管理端分页（关键字匹配姓名/登录账号/工号；status 精确过滤） */
    public Page<UserSnapshot> page(long current, long size, String keyword, String status) {
        return userMapper.selectPage(new Page<>(current, size), new LambdaQueryWrapper<UserSnapshot>()
                .and(StringUtils.hasText(keyword), w -> w
                        .like(UserSnapshot::getName, keyword)
                        .or().like(UserSnapshot::getLoginName, keyword)
                        .or().like(UserSnapshot::getEmployeeNo, keyword))
                .eq(StringUtils.hasText(status), UserSnapshot::getStatus, status)
                .orderByAsc(UserSnapshot::getId));
    }

    /** 用户详情（含部门路径；敏感字段由 Controller 脱敏） */
    public UserSnapshot detail(Long id) {
        UserSnapshot user = findById(id);
        if (user == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        user.setDeptPath(buildDeptPath(user.getPrimaryOrgId()));
        return user;
    }

    /** PENDING 用户资料补全并激活（渠道自动建号的字段缺失用户，D4） */
    public void complete(Long id, String name, String phone, String email, String employeeNo, Long primaryOrgId) {
        UserSnapshot user = detail(id);
        if (!"PENDING".equals(user.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "仅 PENDING 状态用户需要补全");
        }
        if (primaryOrgId != null && orgMapper.selectById(primaryOrgId) == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "组织不存在");
        }
        UserSnapshot update = new UserSnapshot();
        update.setId(id);
        update.setName(name);
        update.setPhone(phone);
        update.setEmail(email);
        update.setEmployeeNo(employeeNo);
        if (primaryOrgId != null) {
            update.setPrimaryOrgId(primaryOrgId);
        }
        update.setIsEmployee(1);
        update.setStatus("ACTIVE");
        userMapper.updateById(update);
    }

    /**
     * 激活/停用。停用即全清会话（含 refresh）立即踢下线；MERGED 用户不可变更。
     *
     * @param active true=激活（DISABLED/PENDING→ACTIVE）；false=停用（→DISABLED）
     */
    public void changeStatus(Long id, boolean active) {
        UserSnapshot user = detail(id);
        if ("MERGED".equals(user.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "已合并用户不可变更状态");
        }
        if (!active && "DISABLED".equals(user.getStatus())) {
            return;
        }
        UserSnapshot update = new UserSnapshot();
        update.setId(id);
        update.setStatus(active ? "ACTIVE" : "DISABLED");
        if (active) {
            update.setIsEmployee(1);
        }
        userMapper.updateById(update);
        if (!active) {
            sessionService.deleteAllSessionsByUser(String.valueOf(id));
        }
    }

    /** 设置 PC 登录账号（唯一性校验，排除自身） */
    public void setLoginAccount(Long id, String loginName) {
        UserSnapshot user = detail(id);
        if ("MERGED".equals(user.getStatus())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "已合并用户不可设置登录账号");
        }
        UserSnapshot occupied = findByLoginName(loginName);
        if (occupied != null && !occupied.getId().equals(id)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "登录账号已被占用");
        }
        UserSnapshot update = new UserSnapshot();
        update.setId(id);
        update.setLoginName(loginName);
        userMapper.updateById(update);
    }

    /** 管理员重置密码：password_updated_at 置 NULL 强制下次登录改密，并全清会话 */
    public void resetPassword(Long id, String passwordHash) {
        UserSnapshot user = detail(id);
        if (user.getLoginName() == null) {
            throw new BizException(ErrorCode.BIZ_ERROR, "该用户未设置登录账号，请先设置登录账号");
        }
        UserSnapshot update = new UserSnapshot();
        update.setId(id);
        update.setPasswordHash(passwordHash);
        update.setPasswordUpdatedAt(null);
        userMapper.updateById(update);
        sessionService.deleteAllSessionsByUser(String.valueOf(id));
    }
}

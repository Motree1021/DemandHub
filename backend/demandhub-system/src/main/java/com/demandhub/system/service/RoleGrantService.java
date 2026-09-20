package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.RoleGrantSaveRequest;
import com.demandhub.system.entity.RoleGrant;
import com.demandhub.system.mapper.RoleGrantMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

/**
 * 业务角色授权（FR-M1-03）：本地维护，仅系统管理员可操作。
 * 授权变更后使目标用户会话失效，1 分钟内生效（用户端自动刷新令牌续期）。
 */
@Service
public class RoleGrantService {

    private final RoleGrantMapper roleGrantMapper;
    private final SessionService sessionService;

    public RoleGrantService(RoleGrantMapper roleGrantMapper, SessionService sessionService) {
        this.roleGrantMapper = roleGrantMapper;
        this.sessionService = sessionService;
    }

    /**
     * 查询用户当前生效的授权记录
     */
    public List<RoleGrant> listEffectiveGrants(String userId) {
        LocalDateTime now = LocalDateTime.now();
        return roleGrantMapper.selectList(new LambdaQueryWrapper<RoleGrant>()
                .eq(RoleGrant::getUserId, userId)
                .and(w -> w.isNull(RoleGrant::getEffectiveFrom).or().le(RoleGrant::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrant::getEffectiveTo).or().ge(RoleGrant::getEffectiveTo, now)));
    }

    /**
     * 用户当前生效的角色编码列表
     */
    public List<String> listEffectiveRoleCodes(String userId) {
        return listEffectiveGrants(userId).stream().map(RoleGrant::getRoleCode).distinct().toList();
    }

    public Page<RoleGrant> page(long current, long size, String userId, String roleCode) {
        return roleGrantMapper.selectPage(new Page<>(current, size), new LambdaQueryWrapper<RoleGrant>()
                .eq(StringUtils.hasText(userId), RoleGrant::getUserId, userId)
                .eq(StringUtils.hasText(roleCode), RoleGrant::getRoleCode, roleCode)
                .orderByDesc(RoleGrant::getId));
    }

    public Long create(RoleGrantSaveRequest req, String grantedBy) {
        ensureNotDuplicated(req, null);
        RoleGrant grant = new RoleGrant();
        applyReq(grant, req);
        grant.setGrantedBy(grantedBy);
        LocalDateTime now = LocalDateTime.now();
        grant.setCreatedAt(now);
        grant.setUpdatedAt(now);
        roleGrantMapper.insert(grant);
        sessionService.deleteSessionsByUser(req.getUserId());
        return grant.getId();
    }

    public void update(RoleGrantSaveRequest req) {
        RoleGrant existing = roleGrantMapper.selectById(req.getId());
        if (existing == null) {
            throw new BizException(ErrorCode.ROLE_GRANT_NOT_FOUND);
        }
        ensureNotDuplicated(req, req.getId());
        applyReq(existing, req);
        existing.setUpdatedAt(LocalDateTime.now());
        roleGrantMapper.updateById(existing);
        sessionService.deleteSessionsByUser(existing.getUserId());
    }

    public void delete(Long id) {
        RoleGrant existing = roleGrantMapper.selectById(id);
        if (existing == null) {
            throw new BizException(ErrorCode.ROLE_GRANT_NOT_FOUND);
        }
        roleGrantMapper.deleteById(id);
        sessionService.deleteSessionsByUser(existing.getUserId());
    }

    private void applyReq(RoleGrant grant, RoleGrantSaveRequest req) {
        grant.setUserId(req.getUserId());
        grant.setRoleCode(req.getRoleCode());
        grant.setOrgId(req.getOrgId());
        grant.setDemandTypeScope(StringUtils.hasText(req.getDemandTypeScope()) ? req.getDemandTypeScope() : null);
        grant.setEffectiveFrom(req.getEffectiveFrom());
        grant.setEffectiveTo(req.getEffectiveTo());
    }

    private void ensureNotDuplicated(RoleGrantSaveRequest req, Long excludeId) {
        LambdaQueryWrapper<RoleGrant> wrapper = new LambdaQueryWrapper<RoleGrant>()
                .eq(RoleGrant::getUserId, req.getUserId())
                .eq(RoleGrant::getRoleCode, req.getRoleCode())
                .ne(excludeId != null, RoleGrant::getId, excludeId);
        if (req.getOrgId() == null) {
            wrapper.isNull(RoleGrant::getOrgId);
        } else {
            wrapper.eq(RoleGrant::getOrgId, req.getOrgId());
        }
        if (req.getDemandTypeScope() == null) {
            wrapper.isNull(RoleGrant::getDemandTypeScope);
        } else {
            wrapper.eq(RoleGrant::getDemandTypeScope, req.getDemandTypeScope());
        }
        Long count = roleGrantMapper.selectCount(wrapper);
        if (count != null && count > 0) {
            throw new BizException(ErrorCode.ROLE_GRANT_DUPLICATED);
        }
    }
}

package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
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

/**
 * 业务角色授权（FR-M1-03）：本地维护，仅系统管理员可操作。
 * 授权变更后使目标用户会话失效，1 分钟内生效（用户端自动刷新令牌续期）。
 * 角色族版：roleCode ∈ ADMIN/EXECUTIVE/MANAGER/HANDLER，按 demand_user_id（OneID）授权。
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
    public List<RoleGrant> listEffectiveGrants(Long demandUserId) {
        LocalDateTime now = LocalDateTime.now();
        return roleGrantMapper.selectList(new LambdaQueryWrapper<RoleGrant>()
                .eq(RoleGrant::getDemandUserId, demandUserId)
                .and(w -> w.isNull(RoleGrant::getEffectiveFrom).or().le(RoleGrant::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrant::getEffectiveTo).or().ge(RoleGrant::getEffectiveTo, now)));
    }

    /**
     * 用户当前生效的角色编码列表
     */
    public List<String> listEffectiveRoleCodes(Long demandUserId) {
        return listEffectiveGrants(demandUserId).stream().map(RoleGrant::getRoleCode).distinct().toList();
    }

    public Page<RoleGrant> page(long current, long size, Long demandUserId, String roleCode) {
        return roleGrantMapper.selectPage(new Page<>(current, size), new LambdaQueryWrapper<RoleGrant>()
                .eq(demandUserId != null, RoleGrant::getDemandUserId, demandUserId)
                .eq(StringUtils.hasText(roleCode), RoleGrant::getRoleCode, roleCode)
                .orderByDesc(RoleGrant::getId));
    }

    public Long create(RoleGrantSaveRequest req, Long grantedBy) {
        ensureNotDuplicated(req, null);
        RoleGrant grant = new RoleGrant();
        applyReq(grant, req);
        grant.setGrantedBy(grantedBy);
        LocalDateTime now = LocalDateTime.now();
        grant.setCreatedAt(now);
        grant.setUpdatedAt(now);
        roleGrantMapper.insert(grant);
        sessionService.deleteSessionsByUser(String.valueOf(req.getDemandUserId()));
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
        sessionService.deleteSessionsByUser(String.valueOf(existing.getDemandUserId()));
    }

    public void delete(Long id) {
        RoleGrant existing = roleGrantMapper.selectById(id);
        if (existing == null) {
            throw new BizException(ErrorCode.ROLE_GRANT_NOT_FOUND);
        }
        // uk_grant 含 is_deleted：回收置为行 id（而非固定 1），保证同元组多次 授权→回收 周期已删行互不撞唯一键；
        // MP @TableLogic 查询过滤 is_deleted=0，行为不变
        roleGrantMapper.update(null, new LambdaUpdateWrapper<RoleGrant>()
                .eq(RoleGrant::getId, id)
                .set(RoleGrant::getIsDeleted, id)
                .set(RoleGrant::getUpdatedAt, LocalDateTime.now()));
        sessionService.deleteSessionsByUser(String.valueOf(existing.getDemandUserId()));
    }

    private void applyReq(RoleGrant grant, RoleGrantSaveRequest req) {
        grant.setDemandUserId(req.getDemandUserId());
        grant.setRoleCode(req.getRoleCode());
        grant.setOrgId(req.getOrgId());
        grant.setDemandTypeScope(StringUtils.hasText(req.getDemandTypeScope()) ? req.getDemandTypeScope() : null);
        grant.setEffectiveFrom(req.getEffectiveFrom());
        grant.setEffectiveTo(req.getEffectiveTo());
    }

    private void ensureNotDuplicated(RoleGrantSaveRequest req, Long excludeId) {
        LambdaQueryWrapper<RoleGrant> wrapper = new LambdaQueryWrapper<RoleGrant>()
                .eq(RoleGrant::getDemandUserId, req.getDemandUserId())
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

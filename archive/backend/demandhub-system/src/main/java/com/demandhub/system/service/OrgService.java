package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.OrgSaveRequest;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.RoleGrant;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.RoleGrantMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 组织管理（FR-M1-02，开发计划任务 4.5）：CRUD + 物化路径维护。
 * - 新增：id 自增回填后按 父path+id/ 生成物化路径；
 * - 修改 parentId：整棵子树路径前缀重算（事务）；
 * - 删除：引用校验（子组织/用户主组织/角色授权/在途与历史需求），外部虚拟组织(900)与根组织禁删。
 */
@Slf4j
@Service
public class OrgService {

    private final OrgSnapshotMapper orgMapper;
    private final UserSnapshotMapper userMapper;
    private final RoleGrantMapper roleGrantMapper;

    public OrgService(OrgSnapshotMapper orgMapper, UserSnapshotMapper userMapper, RoleGrantMapper roleGrantMapper) {
        this.orgMapper = orgMapper;
        this.userMapper = userMapper;
        this.roleGrantMapper = roleGrantMapper;
    }

    /** 新增组织（AUTO 回填 id 后生成物化路径） */
    @Transactional
    public Long create(OrgSaveRequest req) {
        OrgSnapshot parent = requireOrg(req.getParentId());
        OrgSnapshot org = new OrgSnapshot();
        org.setName(req.getName());
        org.setLevel(req.getLevel());
        org.setParentId(parent.getId());
        org.setOrgKind(req.getOrgKind());
        org.setExternalFlag(0);
        org.setExternalDeptId(StringUtils.hasText(req.getExternalDeptId()) ? req.getExternalDeptId() : null);
        org.setStatus("ACTIVE");
        // path 列 NOT NULL：先占位插入拿 AUTO id，再回填真实物化路径
        org.setPath("/");
        orgMapper.insert(org);

        OrgSnapshot pathUpdate = new OrgSnapshot();
        pathUpdate.setId(org.getId());
        pathUpdate.setPath(childPath(parent, org.getId()));
        orgMapper.updateById(pathUpdate);
        log.info("组织新增: id={}, name={}, parent={}", org.getId(), org.getName(), parent.getId());
        return org.getId();
    }

    /** 修改组织；parentId 变更时整棵子树物化路径重算 */
    @Transactional
    public void update(OrgSaveRequest req) {
        OrgSnapshot org = requireOrg(req.getId());
        OrgSnapshot newParent = requireOrg(req.getParentId());
        if (newParent.getId().equals(org.getId())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "父组织不能是自身");
        }

        String oldPath = org.getPath();
        boolean parentChanged = !newParent.getId().equals(org.getParentId());
        if (parentChanged) {
            if (org.getParentId() == null || org.getParentId() == 0) {
                throw new BizException(ErrorCode.PARAM_INVALID, "根组织不允许调整父级");
            }
            String newPath = childPath(newParent, org.getId());
            if (oldPath != null && newPath.startsWith(oldPath)) {
                throw new BizException(ErrorCode.PARAM_INVALID, "不能移动到自身子树下");
            }
            // 子树路径前缀整体替换（含自身）
            orgMapper.rewriteSubtreePath(oldPath, newPath);
            log.info("组织子树路径重算: id={}, {} → {}", org.getId(), oldPath, newPath);
        }

        OrgSnapshot update = new OrgSnapshot();
        update.setId(org.getId());
        update.setName(req.getName());
        update.setLevel(req.getLevel());
        update.setParentId(newParent.getId());
        update.setOrgKind(req.getOrgKind());
        update.setExternalDeptId(StringUtils.hasText(req.getExternalDeptId()) ? req.getExternalDeptId() : null);
        if (StringUtils.hasText(req.getStatus())) {
            update.setStatus(req.getStatus());
        }
        orgMapper.updateById(update);
    }

    /** 删除组织：引用校验（子组织/用户/授权/需求任一引用即拒） */
    public void delete(Long id) {
        OrgSnapshot org = requireOrg(id);
        if (org.getParentId() == null || org.getParentId() == 0) {
            throw new BizException(ErrorCode.PARAM_INVALID, "根组织不允许删除");
        }
        if (org.getId() == UserService.EXTERNAL_ORG_ID) {
            throw new BizException(ErrorCode.PARAM_INVALID, "外部虚拟组织（渠道未映射兜底）不允许删除");
        }
        Long children = orgMapper.selectCount(new LambdaQueryWrapper<OrgSnapshot>()
                .eq(OrgSnapshot::getParentId, id));
        if (children != null && children > 0) {
            throw new BizException(ErrorCode.BIZ_ERROR, "存在子组织，不允许删除");
        }
        Long users = userMapper.selectCount(new LambdaQueryWrapper<UserSnapshot>()
                .eq(UserSnapshot::getPrimaryOrgId, id));
        if (users != null && users > 0) {
            throw new BizException(ErrorCode.BIZ_ERROR, "存在归属用户，不允许删除");
        }
        Long grants = roleGrantMapper.selectCount(new LambdaQueryWrapper<RoleGrant>()
                .eq(RoleGrant::getOrgId, id));
        if (grants != null && grants > 0) {
            throw new BizException(ErrorCode.BIZ_ERROR, "存在角色授权引用，不允许删除");
        }
        Long demands = orgMapper.countDemandReferences(id);
        if (demands != null && demands > 0) {
            throw new BizException(ErrorCode.BIZ_ERROR, "存在需求引用（承接组织），不允许删除");
        }
        orgMapper.deleteById(id);
        log.info("组织删除: id={}, name={}", org.getId(), org.getName());
    }

    private OrgSnapshot requireOrg(Long id) {
        OrgSnapshot org = id == null ? null : orgMapper.selectById(id);
        if (org == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "组织不存在");
        }
        return org;
    }

    private String childPath(OrgSnapshot parent, Long childId) {
        String parentPath = StringUtils.hasText(parent.getPath()) ? parent.getPath() : "/";
        if (!parentPath.endsWith("/")) {
            parentPath = parentPath + "/";
        }
        return parentPath + childId + "/";
    }
}

package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.system.entity.ChannelUserMapping;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelUserMappingMapper;
import com.demandhub.system.sso.SsoProfile;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;

/**
 * 渠道用户匹配引擎（FR-M1-01，开发计划任务 2.2）。
 * 匹配优先级：既有渠道映射 → 手机号精确匹配 > 企微 userid；
 * 命中后刷新映射快照与最后登录；未命中按 D4 自动建 ACTIVE 账号（票据带回企微 userid 即在职员工）；
 * 同手机/同企微关联到不同 OneID 时记录合并提示（conflictUserId），不阻塞登录。
 */
@Slf4j
@Service
public class ChannelUserMatcher {

    private final UserService userService;
    private final ChannelUserMappingMapper mappingMapper;

    public ChannelUserMatcher(UserService userService, ChannelUserMappingMapper mappingMapper) {
        this.userService = userService;
        this.mappingMapper = mappingMapper;
    }

    /**
     * 匹配或建立 OneID，并更新映射与最后登录。
     *
     * @param channelCode 渠道码
     * @param profile     经回源校验的身份（只信服务端 verify 结果）
     */
    public MatchResult match(String channelCode, SsoProfile profile) {
        MatchResult result = new MatchResult();

        // 1. 既有渠道映射直接命中（该渠道身份已绑定过 OneID）
        ChannelUserMapping mapping = findMapping(channelCode, profile.getUserId());
        if (mapping != null) {
            UserSnapshot user = followMerged(mapping);
            if (user != null) {
                // 合并提示：手机号精确命中了另一个 OneID
                UserSnapshot byPhone = followMerged(userService.findByPhone(profile.getPhone()));
                if (byPhone != null && !byPhone.getId().equals(user.getId())) {
                    result.setConflictUserId(byPhone.getId());
                    log.warn("渠道匹配冲突：映射命中 user={}，手机号另命中 user={}，待管理员合并",
                            user.getId(), byPhone.getId());
                }
                refreshMappingSnapshot(mapping, profile);
                result.setUser(user);
                result.setMatchType(mapping.getMatchType());
                userService.touchLastLogin(user.getId(), channelCode);
                return result;
            }
        }

        UserSnapshot byPhone = followMerged(userService.findByPhone(profile.getPhone()));
        UserSnapshot byWecom = followMerged(userService.findByWecomUserid(profile.getUserId()));

        // 2. 手机号精确匹配（优先级高于企微 userid）
        if (byPhone != null) {
            if (byWecom != null && !byWecom.getId().equals(byPhone.getId())) {
                result.setConflictUserId(byWecom.getId());
                log.warn("渠道匹配冲突：手机号命中 user={}，企微 userid 另命中 user={}，待管理员合并",
                        byPhone.getId(), byWecom.getId());
            }
            createMapping(channelCode, profile, byPhone.getId(), "PHONE");
            result.setUser(byPhone);
            result.setMatchType("PHONE");
            userService.touchLastLogin(byPhone.getId(), channelCode);
            return result;
        }

        // 3. 企微 userid 匹配 demand_user.wecom_userid
        if (byWecom != null) {
            createMapping(channelCode, profile, byWecom.getId(), "WECOMID");
            result.setUser(byWecom);
            result.setMatchType("WECOMID");
            userService.touchLastLogin(byWecom.getId(), channelCode);
            return result;
        }

        // 4. 未命中 → D4 自动建号：票据带回企微 userid 即认定在职员工（ACTIVE + is_employee=1）；
        //    无手机且无 userid 的字段缺失票据只兜 PENDING（进待完善队列，不阻塞由 MANUAL 绑定后激活）
        boolean active = StringUtils.hasText(profile.getUserId());
        Long orgId = resolveOrgId(profile.getDeptId());
        UserSnapshot created = userService.createChannelUser(
                StringUtils.hasText(profile.getName()) ? profile.getName() : "渠道用户",
                profile.getPhone(), profile.getUserId(), orgId, active);
        if (active) {
            createMapping(channelCode, profile, created.getId(), "WECOMID");
        }
        log.info("渠道自动建号: userId={}, name={}, status={}, org={}",
                created.getId(), created.getName(), created.getStatus(), orgId);
        result.setUser(created);
        result.setCreatedNew(true);
        result.setMatchType(active ? "WECOMID" : "MANUAL");
        userService.touchLastLogin(created.getId(), channelCode);
        return result;
    }

    /** 渠道部门 ID → demand_org.external_dept_id；未匹配挂外部虚拟组织（900），不阻塞登录提报 */
    private Long resolveOrgId(String deptId) {
        OrgSnapshot org = userService.findOrgByExternalDeptId(deptId);
        return org != null ? org.getId() : UserService.EXTERNAL_ORG_ID;
    }

    private ChannelUserMapping findMapping(String channelCode, String channelUserId) {
        if (!StringUtils.hasText(channelUserId)) {
            return null;
        }
        return mappingMapper.selectOne(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getChannelCode, channelCode)
                .eq(ChannelUserMapping::getChannelUserId, channelUserId));
    }

    /** MERGED 状态登录跳转目标用户；映射随之一并改指目标 OneID */
    private UserSnapshot followMerged(ChannelUserMapping mapping) {
        UserSnapshot user = userService.findById(mapping.getDemandUserId());
        UserSnapshot target = followMerged(user);
        if (target != null && user != null && !target.getId().equals(user.getId())) {
            mapping.setDemandUserId(target.getId());
            mapping.setUpdatedAt(LocalDateTime.now());
            mappingMapper.updateById(mapping);
        }
        return target;
    }

    private UserSnapshot followMerged(UserSnapshot user) {
        if (user != null && "MERGED".equals(user.getStatus()) && user.getMergedToUserId() != null) {
            UserSnapshot target = userService.findById(user.getMergedToUserId());
            log.info("命中 MERGED 用户 {}，跳转目标用户 {}", user.getId(), user.getMergedToUserId());
            return target;
        }
        return user;
    }

    /** 命中后刷新渠道侧回传的姓名/手机/部门快照 */
    private void refreshMappingSnapshot(ChannelUserMapping mapping, SsoProfile profile) {
        mapping.setChannelName(profile.getName());
        mapping.setChannelPhone(profile.getPhone());
        mapping.setChannelDept(StringUtils.hasText(profile.getDeptPath()) ? profile.getDeptPath() : profile.getDeptName());
        mapping.setUpdatedAt(LocalDateTime.now());
        mappingMapper.updateById(mapping);
    }

    private void createMapping(String channelCode, SsoProfile profile, Long demandUserId, String matchType) {
        if (!StringUtils.hasText(profile.getUserId())) {
            return;
        }
        ChannelUserMapping mapping = new ChannelUserMapping();
        mapping.setChannelCode(channelCode);
        mapping.setChannelUserId(profile.getUserId());
        mapping.setDemandUserId(demandUserId);
        mapping.setChannelName(profile.getName());
        mapping.setChannelPhone(profile.getPhone());
        mapping.setChannelDept(StringUtils.hasText(profile.getDeptPath()) ? profile.getDeptPath() : profile.getDeptName());
        mapping.setMatchType(matchType);
        mapping.setBoundAt(LocalDateTime.now());
        mappingMapper.insert(mapping);
    }
}

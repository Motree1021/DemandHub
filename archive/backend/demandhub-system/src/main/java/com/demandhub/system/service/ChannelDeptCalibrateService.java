package com.demandhub.system.service;

import com.demandhub.system.mapper.ChannelDeptUnmappedMapper;
import com.demandhub.system.sso.SsoProfile;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 渠道部门校准服务（任务 3.5）：verify 回传 dept_id 未映射时回流进校准清单，
 * 供 P4 管理端展示（列表/维护 external_dept_id 对照关系）。
 */
@Slf4j
@Service
public class ChannelDeptCalibrateService {

    private final ChannelDeptUnmappedMapper unmappedMapper;

    public ChannelDeptCalibrateService(ChannelDeptUnmappedMapper unmappedMapper) {
        this.unmappedMapper = unmappedMapper;
    }

    /** 记录一次未映射命中（幂等累加；失败仅告警不阻塞登录主链路） */
    public void record(String channelCode, SsoProfile profile) {
        try {
            unmappedMapper.upsertHit(channelCode, profile.getDeptId(),
                    profile.getDeptName(), profile.getDeptPath(), profile.getUserId());
            log.info("渠道部门未映射回流校准清单: channel={}, deptId={}, deptName={}, channelUserId={}",
                    channelCode, profile.getDeptId(), profile.getDeptName(), profile.getUserId());
        } catch (Exception e) {
            log.warn("渠道部门未映射记录失败（不阻塞登录）: channel={}, deptId={}, err={}",
                    channelCode, profile.getDeptId(), e.getMessage());
        }
    }
}

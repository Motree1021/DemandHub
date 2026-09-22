package com.demandhub.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.MockUserVO;
import com.demandhub.system.entity.ChannelUserMapping;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelUserMappingMapper;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import com.demandhub.system.sso.MockTicketVerifier;
import com.demandhub.system.sso.SsoProfile;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.Data;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.Serializable;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Mock 创金零售 SSO（仅 dev：demandhub.channel-sso.mock=true）。
 * 模拟创金零售侧行为：凭自身企微登录态签发一次性 ticket（Redis 存 60s），
 * DemandHub 经 {@link MockTicketVerifier} 回源消费（一次性）。P3 扩展过期/重放/字段缺失等场景页。
 */
@Tag(name = "Mock 渠道SSO（仅dev）")
@RestController
@RequestMapping("/system/mock-sso")
@ConditionalOnProperty(name = "demandhub.channel-sso.mock", havingValue = "true", matchIfMissing = true)
public class MockChannelSsoController {

    private static final long TICKET_TTL_SECONDS = 60;

    private final ChannelUserMappingMapper mappingMapper;
    private final UserSnapshotMapper userMapper;
    private final OrgSnapshotMapper orgMapper;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public MockChannelSsoController(ChannelUserMappingMapper mappingMapper,
                                    UserSnapshotMapper userMapper,
                                    OrgSnapshotMapper orgMapper,
                                    StringRedisTemplate redis) {
        this.mappingMapper = mappingMapper;
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
        this.redis = redis;
    }

    @Operation(summary = "Mock 创金零售入口：可选用户列表（已建 CHUANGJIN_LS 映射的 ACTIVE 用户）")
    @GetMapping("/entry")
    public Result<List<MockUserVO>> entry() {
        List<ChannelUserMapping> mappings = mappingMapper.selectList(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getChannelCode, "CHUANGJIN_LS"));
        Map<Long, UserSnapshot> users = userMapper.selectBatchIds(
                        mappings.stream().map(ChannelUserMapping::getDemandUserId).distinct().toList())
                .stream().collect(Collectors.toMap(UserSnapshot::getId, Function.identity()));
        Map<Long, String> orgNames = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshot::getId, OrgSnapshot::getName, (a, b) -> a));
        List<MockUserVO> list = mappings.stream()
                .map(m -> {
                    UserSnapshot u = users.get(m.getDemandUserId());
                    if (u == null || !"ACTIVE".equals(u.getStatus())) {
                        return null;
                    }
                    MockUserVO vo = new MockUserVO();
                    vo.setChannelUserId(m.getChannelUserId());
                    vo.setName(u.getName());
                    vo.setOrgName(u.getPrimaryOrgId() == null ? null : orgNames.get(u.getPrimaryOrgId()));
                    return vo;
                })
                .filter(java.util.Objects::nonNull)
                .toList();
        return Result.ok(list);
    }

    @Operation(summary = "Mock 签发一次性 ticket（60s 有效；channelUserId 未建档时可携带姓名/手机模拟新人员工）")
    @PostMapping("/ticket")
    public Result<IssuedTicketVO> issue(@RequestBody TicketIssueRequest request) {
        if (!StringUtils.hasText(request.getChannelUserId())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "channelUserId 不能为空");
        }
        SsoProfile profile = buildProfile(request);
        String ticket = UUID.randomUUID().toString().replace("-", "");
        try {
            redis.opsForValue().set(MockTicketVerifier.TICKET_KEY_PREFIX + ticket,
                    objectMapper.writeValueAsString(profile), Duration.ofSeconds(TICKET_TTL_SECONDS));
        } catch (Exception e) {
            throw new IllegalStateException("Mock 票据签发失败", e);
        }
        IssuedTicketVO vo = new IssuedTicketVO();
        vo.setTicket(ticket);
        vo.setExpiresIn(TICKET_TTL_SECONDS);
        return Result.ok(vo);
    }

    /** 已建档渠道用户按库内信息回源；未建档按请求参数构造（模拟创金零售侧新员工） */
    private SsoProfile buildProfile(TicketIssueRequest request) {
        ChannelUserMapping mapping = mappingMapper.selectOne(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getChannelCode, "CHUANGJIN_LS")
                .eq(ChannelUserMapping::getChannelUserId, request.getChannelUserId()));
        UserSnapshot user = mapping != null ? userMapper.selectById(mapping.getDemandUserId()) : null;
        // dev 种子用户同时写了 demand_user.wecom_userid，映射缺失时兜底直查
        if (user == null) {
            user = userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>()
                    .eq(UserSnapshot::getWecomId, request.getChannelUserId()));
        }

        SsoProfile profile = new SsoProfile();
        profile.setUserId(request.getChannelUserId());
        if (user != null) {
            profile.setName(StringUtils.hasText(request.getName()) ? request.getName() : user.getName());
            profile.setPhone(StringUtils.hasText(request.getPhone()) ? request.getPhone() : user.getPhone());
            profile.setEmployeeNo(user.getEmployeeNo());
            profile.setEmail(user.getEmail());
            if (user.getPrimaryOrgId() != null) {
                OrgSnapshot org = orgMapper.selectById(user.getPrimaryOrgId());
                if (org != null) {
                    profile.setDeptId(org.getExternalDeptId());
                    profile.setDeptName(org.getName());
                }
            }
        } else {
            profile.setName(StringUtils.hasText(request.getName()) ? request.getName() : "渠道新员工");
            profile.setPhone(request.getPhone());
            profile.setDeptId(request.getDeptId());
            profile.setDeptName(request.getDeptName());
        }
        return profile;
    }

    @Data
    public static class TicketIssueRequest implements Serializable {
        /** 渠道侧用户 ID（Mock 企微 userid，如 wq_u_mgr_tech；新人员工可自定义） */
        private String channelUserId;
        /** 以下为新人员工可选字段（已建档用户忽略，按库内信息回源） */
        private String name;
        private String phone;
        private String deptId;
        private String deptName;
    }

    @Data
    public static class IssuedTicketVO implements Serializable {
        private String ticket;
        private Long expiresIn;
    }
}

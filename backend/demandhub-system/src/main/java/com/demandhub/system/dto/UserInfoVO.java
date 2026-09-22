package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

/**
 * 当前用户信息（/auth/me 与登录响应共用）
 */
@Data
public class UserInfoVO implements Serializable {

    private Long id;

    private String userId;

    private String name;

    private Long primaryOrgId;

    private String orgName;

    private String deptPath;

    /** 登录渠道（WEB/CHUANGJIN_LS） */
    private String channel;

    /** 生效中的业务角色编码（角色族：ADMIN/EXECUTIVE/MANAGER/HANDLER） */
    private List<String> roles;

    /** 生效授权的需求类型集合（逗号多选展开去重；空 = 跟随角色默认不限类型） */
    private List<String> typeScopes;

    /** 生效中的授权明细 */
    private List<GrantVO> grants;

    /** 是否需要强制改密（有 PC 账号且 password_updated_at 为 NULL） */
    private Boolean mustChangePassword;

    /** 降级只读会话标识（预留） */
    private Boolean readOnly;

    @Data
    public static class GrantVO implements Serializable {
        private String roleCode;
        private Long orgId;
        private String orgName;
        private String demandTypeScope;
    }
}

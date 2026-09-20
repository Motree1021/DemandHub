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

    /** 生效中的业务角色编码 */
    private List<String> roles;

    /** 生效中的授权明细 */
    private List<GrantVO> grants;

    /** 降级只读会话标识（权限中心不可用时为 true） */
    private Boolean readOnly;

    @Data
    public static class GrantVO implements Serializable {
        private String roleCode;
        private Long orgId;
        private String orgName;
        private String demandTypeScope;
    }
}

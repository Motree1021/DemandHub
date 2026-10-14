package com.demandhub.system.sso;

import lombok.Data;

import java.io.Serializable;

/**
 * 渠道 SSO 校验回源身份（对应对接标准 v2.0 §3.3 verify 成功响应的 user 节点）。
 * DemandHub 只信任经服务端回源校验的该身份，绝不解析/信任 URL 明文身份。
 */
@Data
public class SsoProfile implements Serializable {

    /** 渠道侧稳定唯一 ID（创金零售直接回传企微 userid，必填） */
    private String userId;

    /** 姓名（必填） */
    private String name;

    /** 手机号（建议；受权限限制可空，不阻塞登录） */
    private String phone;

    /** 渠道侧部门 ID（企微部门 ID，用于 demand_org.external_dept_id 映射） */
    private String deptId;

    private String deptName;

    private String deptPath;

    /** 工号（可选） */
    private String employeeNo;

    /** 邮箱（可选） */
    private String email;
}

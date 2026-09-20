package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 一期 Mock 登录页可选用户（仅开发期使用）
 */
@Data
public class MockUserVO implements Serializable {

    private String userId;

    private String name;

    private String orgName;

    /** Mock 授权码，前端直接携带回调 */
    private String mockCode;
}

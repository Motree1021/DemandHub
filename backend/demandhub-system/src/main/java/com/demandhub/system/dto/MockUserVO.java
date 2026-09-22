package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * Mock 创金零售入口的可选用户（仅 dev：模拟"创金零售"侧已有企微登录态的员工）
 */
@Data
public class MockUserVO implements Serializable {

    /** 渠道侧用户 ID（Mock 企微 userid，如 wq_u_mgr_tech） */
    private String channelUserId;

    private String name;

    private String orgName;
}

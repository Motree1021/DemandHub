package com.demandhub.system.integration.pcenter.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 权限中心用户模型（IR-06）
 */
@Data
public class PcUser implements Serializable {

    /** 权限中心数值主键（本地镜像沿用，保证业务表引用稳定） */
    private Long id;

    private String userId;

    private String name;

    private String wecomId;

    private String employeeNo;

    private Long primaryOrgId;

    private String deptPath;

    private String phone;

    private String email;

    /** ACTIVE/LEFT */
    private String status;
}

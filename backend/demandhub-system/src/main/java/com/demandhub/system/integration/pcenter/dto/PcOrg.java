package com.demandhub.system.integration.pcenter.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 权限中心组织节点模型（IR-07）
 */
@Data
public class PcOrg implements Serializable {

    private Long orgId;

    private String name;

    /** LINE/DEPT/GROUP */
    private String level;

    private Long parentId;

    /** 物化路径，如 /100/110 */
    private String path;

    /** REPORTER/ASSIGNER/BOTH */
    private String orgKind;

    private String status;
}

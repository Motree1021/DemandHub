package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.io.Serializable;

/**
 * 组织保存请求（FR-M1-02，管理端组织管理）。
 * 新增时不带 id；修改时带 id。parentId 变更触发子树物化路径重算。
 */
@Data
public class OrgSaveRequest implements Serializable {

    /** 修改时必填 */
    private Long id;

    @NotBlank(message = "组织名称不能为空")
    private String name;

    /** LINE/DEPT/GROUP */
    @NotBlank(message = "组织层级不能为空")
    @Pattern(regexp = "LINE|DEPT|GROUP", message = "非法组织层级")
    private String level;

    /** 父组织；新增根组织留空（仅允许一个根，由删除校验保护） */
    @NotNull(message = "父组织不能为空")
    private Long parentId;

    /** REPORTER/ASSIGNER/BOTH */
    @NotBlank(message = "组织类型不能为空")
    @Pattern(regexp = "REPORTER|ASSIGNER|BOTH", message = "非法组织类型")
    private String orgKind;

    /** 渠道侧部门ID（创金零售/企微部门ID），票据登录部门映射用 */
    private String externalDeptId;

    /** ACTIVE/DISABLED（仅修改时有效） */
    @Pattern(regexp = "ACTIVE|DISABLED", message = "非法状态")
    private String status;
}

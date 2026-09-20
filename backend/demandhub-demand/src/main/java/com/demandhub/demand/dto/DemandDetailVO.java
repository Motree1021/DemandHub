package com.demandhub.demand.dto;

import com.demandhub.demand.entity.AttachmentEntity;
import com.demandhub.demand.entity.DemandEntity;
import lombok.Data;

import java.util.List;

/**
 * 需求详情（拼装扩展表 + 姓名/组织 + 附件 + 当前用户可用操作列表）
 */
@Data
public class DemandDetailVO {

    private DemandEntity demand;

    /** 按类型的扩展行（demand_ext_tech/material/training） */
    private Object ext;

    private String typeName;

    private String submitterName;

    private String actualDemanderName;

    private String assigneeOrgName;

    private String assigneeUserName;

    private List<AttachmentEntity> attachments;

    /** 当前用户对该需求可执行的动作 key 列表（按钮显隐依据） */
    private List<String> availableActions;

    /** 已挂起天数（未挂起为 null） */
    private Long holdDays;
}

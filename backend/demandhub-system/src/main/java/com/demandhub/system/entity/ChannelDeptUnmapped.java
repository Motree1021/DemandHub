package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 渠道部门未映射校准清单（channel_dept_unmapped，任务 3.5）。
 * verify 回传 dept_id 在 demand_org.external_dept_id 查不到时回流记录，
 * 用户挂外部虚拟组织(900)不阻塞登录提报；本表供 P4 管理端展示与校准维护。
 */
@Data
@TableName("channel_dept_unmapped")
public class ChannelDeptUnmapped implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String channelCode;

    /** 渠道侧部门 ID（verify 回传） */
    private String deptId;

    private String deptName;

    private String deptPath;

    /** 最近一个命中该部门的渠道用户 ID（排查样本） */
    private String sampleChannelUserId;

    /** 命中次数（每次未映射登录 +1） */
    private Integer hitCount;

    private LocalDateTime firstSeenAt;

    private LocalDateTime lastSeenAt;
}

package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 渠道用户到 OneID 映射（channel_user_mapping）。
 * (channel_code, channel_user_id) 唯一；CHUANGJIN_LS 的 channel_user_id 存企微 userid。
 */
@Data
@TableName("channel_user_mapping")
public class ChannelUserMapping implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String channelCode;

    /** 渠道侧用户唯一ID（CHUANGJIN_LS 存企微 userid） */
    private String channelUserId;

    /** 映射到的 DemandHub OneID */
    private Long demandUserId;

    /** 渠道侧回传的姓名/手机/部门快照（校验时刷新） */
    private String channelName;

    private String channelPhone;

    private String channelDept;

    /** PHONE/WECOMID/MANUAL */
    private String matchType;

    private LocalDateTime boundAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

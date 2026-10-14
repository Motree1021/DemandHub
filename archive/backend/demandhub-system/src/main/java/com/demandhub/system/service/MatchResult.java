package com.demandhub.system.service;

import com.demandhub.system.entity.UserSnapshot;
import lombok.Data;

/**
 * 渠道匹配结果（FR-M1-01）。
 */
@Data
public class MatchResult {

    /** 命中的 OneID 用户（已跟随 MERGED 跳转目标） */
    private UserSnapshot user;

    /** PHONE/WECOMID/MANUAL（新映射的匹配方式；命中既有映射时为其原 matchType） */
    private String matchType;

    /** 是否本次自动建号 */
    private boolean createdNew;

    /**
     * 合并提示：检测到同手机/同企微 userid 关联到另一个 OneID 时记录其 ID，
     * 供管理端合并队列使用（不阻塞本次登录）。
     */
    private Long conflictUserId;
}

package com.demandhub.notification.service;

import java.util.List;

/**
 * 通知类型常量（SRS FR-M7-01/03）。
 * 待办提醒 TODO 为关键通知，用户不可关闭；其余类型可在通知偏好中关闭。
 */
public final class NotifyTypes {

    /** 待办提醒（不可关闭）：提交待受理、退回补充、评审/验收打回等需要行动的通知 */
    public static final String TODO = "TODO";
    /** 状态变更 */
    public static final String STATUS_CHANGE = "STATUS_CHANGE";
    /** @我 */
    public static final String MENTION = "MENTION";
    /** 任务分派 */
    public static final String ASSIGN = "ASSIGN";
    /** 评审请求 */
    public static final String REVIEW_REQUEST = "REVIEW_REQUEST";
    /** 验收请求 */
    public static final String ACCEPTANCE_REQUEST = "ACCEPTANCE_REQUEST";
    /** SLA 告警 */
    public static final String SLA_ALERT = "SLA_ALERT";

    /** 全部类型（偏好设置页展示用） */
    public static final List<String> ALL = List.of(
            TODO, STATUS_CHANGE, MENTION, ASSIGN, REVIEW_REQUEST, ACCEPTANCE_REQUEST, SLA_ALERT);

    private NotifyTypes() {
    }

    public static boolean isClosable(String notifyType) {
        return ALL.contains(notifyType) && !TODO.equals(notifyType);
    }
}

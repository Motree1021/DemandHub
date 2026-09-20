package com.demandhub.common.context;

/**
 * 统一用户上下文：请求级 ThreadLocal，必须在过滤器结束时清理
 */
public final class UserContext {

    private static final ThreadLocal<CurrentUser> HOLDER = new ThreadLocal<>();

    private UserContext() {
    }

    public static void set(CurrentUser user) {
        HOLDER.set(user);
    }

    public static CurrentUser get() {
        return HOLDER.get();
    }

    /** 当前用户数值 ID；未登录返回 0（与历史占位行为一致） */
    public static Long currentUserId() {
        CurrentUser u = HOLDER.get();
        return u == null || u.getId() == null ? 0L : u.getId();
    }

    public static boolean hasRole(String role) {
        CurrentUser u = HOLDER.get();
        return u != null && u.hasRole(role);
    }

    public static void clear() {
        HOLDER.remove();
    }
}

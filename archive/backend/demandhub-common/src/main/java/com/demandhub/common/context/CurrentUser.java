package com.demandhub.common.context;

import lombok.Data;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/**
 * 当前登录用户信息（由网关注入请求头，业务服务 UserContextFilter 解析后放入 ThreadLocal）
 */
@Data
public class CurrentUser implements Serializable {

    /** 用户数值 ID（demand_user.id，OneID） */
    private Long id;

    /** 用户唯一 ID（String.valueOf(OneID)） */
    private String userId;

    /** 业务角色编码列表（角色族：ADMIN/EXECUTIVE/MANAGER/HANDLER） */
    private List<String> roles = new ArrayList<>();

    /** 登录渠道（WEB/CHUANGJIN_LS），由会话 claims 经网关注入，不信任前端传值 */
    private String channel;

    public boolean hasRole(String role) {
        return roles != null && roles.contains(role);
    }

    /** 超级管理员：按产品决策放行全部业务操作与数据范围 */
    public boolean isAdmin() {
        return hasRole("ADMIN");
    }
}

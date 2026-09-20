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

    /** 用户数值 ID（对应 demand_user_snapshot.id / 权限中心数值主键） */
    private Long id;

    /** 权限中心用户唯一 ID，如 u_admin_001 */
    private String userId;

    /** 业务角色编码列表：ADMIN/EXECUTIVE/DEMAND_MANAGER/HANDLER/REPORTER */
    private List<String> roles = new ArrayList<>();

    public boolean hasRole(String role) {
        return roles != null && roles.contains(role);
    }
}

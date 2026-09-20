package com.demandhub.demand.service;

import lombok.Data;

import java.io.Serializable;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * 当前用户的数据范围（FR-M1-04）
 */
@Data
public class DataScope implements Serializable {

    /** 全零售线可见（需求管理者 EXECUTIVE） */
    private boolean bypass;

    /** 无任何业务数据权限（无角色或仅系统管理员） */
    private boolean noAccess;

    /** 用户数值 ID（REPORTER 过滤本人提报用） */
    private Long userId;

    /** 是否含提报人视角（REPORTER：仅看本人提报） */
    private boolean reporter;

    /** 承接组织子树并集（HANDLER/DEMAND_MANAGER） */
    private Set<Long> orgIds = new LinkedHashSet<>();

    public static DataScope bypass() {
        DataScope s = new DataScope();
        s.setBypass(true);
        return s;
    }

    public static DataScope noAccess() {
        DataScope s = new DataScope();
        s.setNoAccess(true);
        return s;
    }
}

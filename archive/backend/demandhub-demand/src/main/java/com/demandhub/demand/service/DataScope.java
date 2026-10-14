package com.demandhub.demand.service;

import lombok.Data;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * 当前用户的数据范围（FR-M1-05，角色族三维版：角色族 × 组织子树 × 类型集合）
 */
@Data
public class DataScope implements Serializable {

    /** 全零售线可见（需求管理者 EXECUTIVE） */
    private boolean bypass;

    /** 无任何业务数据权限（无角色或仅系统管理员） */
    private boolean noAccess;

    /** 用户数值 ID（提报人视角过滤本人提报用） */
    private Long userId;

    /** 是否含提报人视角（不设提报人角色，任何登录用户均可看自己提报的需求） */
    private boolean reporter;

    /** 类型 → 承接组织子树并集（MANAGER/HANDLER 授权按 demand_type_scope 分列） */
    private Map<String, Set<Long>> orgIdsByType = new LinkedHashMap<>();

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

    /** 全部类型的组织并集（工时装机等跨类型统计用） */
    public Set<Long> unionOrgIds() {
        Set<Long> all = new LinkedHashSet<>();
        orgIdsByType.values().forEach(all::addAll);
        return all;
    }
}

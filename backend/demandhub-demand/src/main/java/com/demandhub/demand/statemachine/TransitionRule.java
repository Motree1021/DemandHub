package com.demandhub.demand.statemachine;

import java.util.Set;

/**
 * 一条合法流转规则（配置化数据，非硬编码分支）。
 *
 * @param from   当前状态（ON_HOLD 仅用于 RESUME 规则）
 * @param event  触发事件
 * @param to     目标状态；null 表示“主状态不变”（CHANGE_TYPE）或“恢复挂起前状态”（RESUME）
 * @param roles  允许触发的业务角色（任一）；空集合表示不校验角色（由业务层自行控制）
 * @param remark 规则说明
 */
public record TransitionRule(DemandStatus from, DemandEvent event, DemandStatus to,
                             Set<String> roles, String remark) {
}

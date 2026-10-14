package com.demandhub.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.agent.entity.UserSnapshotView;

/**
 * 单体合并后与 demandhub-demand 同名 Mapper 区分（Spring Bean 名按简单类名生成）
 */
public interface AgentUserSnapshotViewMapper extends BaseMapper<UserSnapshotView> {
}

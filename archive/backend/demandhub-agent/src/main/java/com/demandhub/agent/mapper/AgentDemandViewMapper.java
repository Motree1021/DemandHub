package com.demandhub.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.agent.entity.DemandView;

/**
 * 单体合并后与 demandhub-notification 同名 Mapper 区分（Spring Bean 名按简单类名生成）
 */
public interface AgentDemandViewMapper extends BaseMapper<DemandView> {
}

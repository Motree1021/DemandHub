package com.demandhub.demand.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.demand.entity.RoleGrantView;
import org.apache.ibatis.annotations.Select;

import java.util.Map;

public interface RoleGrantViewMapper extends BaseMapper<RoleGrantView> {

    /**
     * 授权版本号（数据范围缓存键用）：授权 新增/变更/回收 都会改变 count 或 max(updated_at)，
     * 使旧缓存键立即失效，授权调整即时生效（FR-M1-03：1 分钟内生效）。
     */
    @Select("SELECT COUNT(*) AS cnt, COALESCE(MAX(updated_at), '') AS ver FROM demand_role_grant "
            + "WHERE demand_user_id = #{userId} AND is_deleted = 0")
    Map<String, Object> grantVersion(Long userId);
}

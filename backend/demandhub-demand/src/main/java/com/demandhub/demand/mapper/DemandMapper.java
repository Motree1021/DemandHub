package com.demandhub.demand.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.demand.entity.DemandEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface DemandMapper extends BaseMapper<DemandEntity> {

    /** 状态机流转前加行锁（同事务串行化同一需求的并发流转） */
    @Select("SELECT * FROM demand WHERE id = #{id} AND is_deleted = 0 FOR UPDATE")
    DemandEntity selectForUpdate(@Param("id") Long id);
}

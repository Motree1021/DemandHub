package com.demandhub.demand.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.demand.entity.CommentEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CommentMapper extends BaseMapper<CommentEntity> {
}

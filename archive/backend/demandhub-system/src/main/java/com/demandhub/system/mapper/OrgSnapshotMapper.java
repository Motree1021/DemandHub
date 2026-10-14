package com.demandhub.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.system.entity.OrgSnapshot;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

public interface OrgSnapshotMapper extends BaseMapper<OrgSnapshot> {

    /** 需求表承接组织引用计数（同库只读，组织删除引用校验用） */
    @Select("SELECT COUNT(*) FROM demand WHERE assignee_org_id = #{orgId} AND is_deleted = 0")
    Long countDemandReferences(@Param("orgId") Long orgId);

    /** 子树物化路径前缀整体替换（parentId 变更触发；含子树内所有节点） */
    @Update("UPDATE demand_org SET path = CONCAT(#{newPath}, SUBSTRING(path, LENGTH(#{oldPath}) + 1)) "
            + "WHERE path LIKE CONCAT(#{oldPath}, '%')")
    int rewriteSubtreePath(@Param("oldPath") String oldPath, @Param("newPath") String newPath);
}

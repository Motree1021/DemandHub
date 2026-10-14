package com.demandhub.system.mapper;

import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * 用户合并的数据迁移（开发计划任务 2.3）。
 * 业务表与系统库同库，合并为系统侧管理动作，故用原生 SQL 直改（清单：需求/评论/工时/分派/映射，
 * 以及同源的用户所有数据：方案/评审/流转日志/草稿/附件）。
 */
public interface UserMergeMapper {

    // ---------- 影响预览（合并对话框二次确认用） ----------

    @Select("SELECT (SELECT COUNT(*) FROM demand WHERE submitter_id=#{sourceId} OR actual_demander_id=#{sourceId} " +
            "OR assignee_user_id=#{sourceId} OR created_by=#{sourceId} OR updated_by=#{sourceId}) AS demands, " +
            "(SELECT COUNT(*) FROM `comment` WHERE author_id=#{sourceId}) AS comments, " +
            "(SELECT COUNT(*) FROM effort_log WHERE user_id=#{sourceId}) AS efforts, " +
            "(SELECT COUNT(*) FROM assignment WHERE assignee_id=#{sourceId} OR dispatcher_id=#{sourceId}) AS assignments, " +
            "(SELECT COUNT(*) FROM channel_user_mapping WHERE demand_user_id=#{sourceId}) AS mappings, " +
            "(SELECT COUNT(*) FROM demand_role_grant WHERE demand_user_id=#{sourceId} AND is_deleted=0) AS grants")
    java.util.Map<String, Long> preview(@Param("sourceId") Long sourceId);

    // ---------- 需求 ----------

    @Update("UPDATE demand SET submitter_id=#{targetId} WHERE submitter_id=#{sourceId}")
    int migrateDemandSubmitter(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand SET actual_demander_id=#{targetId} WHERE actual_demander_id=#{sourceId}")
    int migrateDemandActualDemander(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand SET assignee_user_id=#{targetId} WHERE assignee_user_id=#{sourceId}")
    int migrateDemandAssignee(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand SET created_by=#{targetId} WHERE created_by=#{sourceId}")
    int migrateDemandCreatedBy(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand SET updated_by=#{targetId} WHERE updated_by=#{sourceId}")
    int migrateDemandUpdatedBy(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    // ---------- 评论 / 工时 / 分派 ----------

    @Update("UPDATE `comment` SET author_id=#{targetId} WHERE author_id=#{sourceId}")
    int migrateCommentAuthor(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE effort_log SET user_id=#{targetId} WHERE user_id=#{sourceId}")
    int migrateEffortUser(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE assignment SET assignee_id=#{targetId} WHERE assignee_id=#{sourceId}")
    int migrateAssignmentAssignee(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE assignment SET dispatcher_id=#{targetId} WHERE dispatcher_id=#{sourceId}")
    int migrateAssignmentDispatcher(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    // ---------- 渠道映射 ----------

    @Update("UPDATE channel_user_mapping SET demand_user_id=#{targetId} WHERE demand_user_id=#{sourceId}")
    int migrateChannelMapping(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    // ---------- 同源用户所有数据（方案/评审/流转日志/草稿/附件） ----------

    @Update("UPDATE solution SET author_id=#{targetId} WHERE author_id=#{sourceId}")
    int migrateSolutionAuthor(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE review SET reviewer_id=#{targetId} WHERE reviewer_id=#{sourceId}")
    int migrateReviewReviewer(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand_transition_log SET operator_id=#{targetId} WHERE operator_id=#{sourceId}")
    int migrateTransitionOperator(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE demand_draft SET user_id=#{targetId} WHERE user_id=#{sourceId}")
    int migrateDraftUser(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    @Update("UPDATE attachment SET uploaded_by=#{targetId} WHERE uploaded_by=#{sourceId}")
    int migrateAttachmentUploader(@Param("sourceId") Long sourceId, @Param("targetId") Long targetId);

    /** 源用户授权逻辑删除：不自动继承到目标用户，避免静默扩权（需要时由管理员重新授权）。置行 id 与 uk_grant 约定一致 */
    @Update("UPDATE demand_role_grant SET is_deleted=id, updated_at=NOW(3) WHERE demand_user_id=#{sourceId} AND is_deleted=0")
    int retireSourceGrants(@Param("sourceId") Long sourceId);
}

package com.demandhub.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demandhub.system.entity.ChannelDeptUnmapped;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;

public interface ChannelDeptUnmappedMapper extends BaseMapper<ChannelDeptUnmapped> {

    /** 未映射部门回流：首次插入，重复命中累加 hit_count 并刷新快照（uk_channel_dept 唯一键） */
    @Insert("INSERT INTO channel_dept_unmapped(channel_code, dept_id, dept_name, dept_path, sample_channel_user_id, hit_count) "
            + "VALUES(#{channelCode}, #{deptId}, #{deptName}, #{deptPath}, #{sampleChannelUserId}, 1) "
            + "ON DUPLICATE KEY UPDATE hit_count = hit_count + 1, "
            + "dept_name = VALUES(dept_name), dept_path = VALUES(dept_path), "
            + "sample_channel_user_id = VALUES(sample_channel_user_id)")
    int upsertHit(@Param("channelCode") String channelCode,
                  @Param("deptId") String deptId,
                  @Param("deptName") String deptName,
                  @Param("deptPath") String deptPath,
                  @Param("sampleChannelUserId") String sampleChannelUserId);
}

package com.demandhub.demand.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

/**
 * 需求编号生成器（FR-M2-06）：{TYPE}-{YYYYMMDD}-{NNN}，按类型按日流水。
 * 计数器存 demand_no_seq 表，自增与需求插入在同一数据库事务内：
 * 提交失败回滚时序号自动返还，已提交的编号严格连续无跳号；
 * 计数行 UPDATE 行锁串行化同类型同日并发，保证无重号；DB uk_demand_no 唯一索引兜底。
 */
@Service
public class DemandNoGenerator {

    private final JdbcTemplate jdbc;

    public DemandNoGenerator(JdbcTemplate jdbcTemplate) {
        this.jdbc = jdbcTemplate;
    }

    /**
     * 取下一个编号（须在外层事务内调用，自增随事务提交/回滚）。
     */
    public String next(String typeCode) {
        String day = LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE);
        String key = typeCode + ":" + day;
        int rows = jdbc.update("UPDATE demand_no_seq SET seq_value = seq_value + 1 WHERE seq_key = ?", key);
        if (rows == 0) {
            // 当日首次：以 demand 表存量最大序号初始化（兼容历史数据），并发初始化由主键 + INSERT IGNORE 裁决
            String like = typeCode + "-" + day + "-%";
            Integer max = jdbc.queryForObject(
                    "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(demand_no, '-', -1) AS UNSIGNED)), 0) "
                            + "FROM demand WHERE demand_no LIKE ?", Integer.class, like);
            jdbc.update("INSERT IGNORE INTO demand_no_seq(seq_key, seq_value) VALUES(?, ?)", key, max == null ? 0 : max);
            jdbc.update("UPDATE demand_no_seq SET seq_value = seq_value + 1 WHERE seq_key = ?", key);
        }
        Long seq = jdbc.queryForObject("SELECT seq_value FROM demand_no_seq WHERE seq_key = ?", Long.class, key);
        if (seq == null) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "需求编号生成失败");
        }
        return String.format("%s-%s-%03d", typeCode, day, seq);
    }
}

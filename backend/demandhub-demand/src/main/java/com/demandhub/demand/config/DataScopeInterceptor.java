package com.demandhub.demand.config;

import com.baomidou.mybatisplus.core.toolkit.PluginUtils;
import com.baomidou.mybatisplus.extension.plugins.inner.InnerInterceptor;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.demand.service.DataScope;
import com.demandhub.demand.service.DataScopeService;
import lombok.extern.slf4j.Slf4j;
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.operators.conditional.AndExpression;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.select.PlainSelect;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.session.ResultHandler;
import org.apache.ibatis.session.RowBounds;

import java.sql.SQLException;
import java.util.Locale;

/**
 * 数据权限拦截器（FR-M1-04 / NFR-08）：
 * 对 demand 表的 SELECT 自动追加当前用户数据范围条件，前端不可绕过；
 * 未登录上下文（Job/内部调用）不追加。
 */
@Slf4j
public class DataScopeInterceptor implements InnerInterceptor {

    private static final String DEMAND_TABLE = "demand";

    private final DataScopeService dataScopeService;

    public DataScopeInterceptor(DataScopeService dataScopeService) {
        this.dataScopeService = dataScopeService;
    }

    @Override
    public void beforeQuery(Executor executor, MappedStatement ms, Object parameter,
                            RowBounds rowBounds, ResultHandler resultHandler, BoundSql boundSql) throws SQLException {
        CurrentUser user = UserContext.get();
        if (user == null) {
            return;
        }
        String sql = boundSql.getSql();
        if (sql == null || !sql.toLowerCase(Locale.ROOT).trim().startsWith("select")) {
            return;
        }
        try {
            Statement statement = CCJSqlParserUtil.parse(sql);
            if (!(statement instanceof PlainSelect plainSelect)
                    || !(plainSelect.getFromItem() instanceof net.sf.jsqlparser.schema.Table table)
                    || !DEMAND_TABLE.equalsIgnoreCase(table.getName())) {
                return;
            }
            // 有别名时条件列加别名前缀
            String prefix = table.getAlias() != null ? table.getAlias().getName() + "." : "";
            DataScope scope = dataScopeService.currentScope(user);
            String condition = dataScopeService.buildCondition(scope, prefix);
            if (condition == null) {
                return;
            }
            Expression extra = CCJSqlParserUtil.parseCondExpression(condition);
            plainSelect.setWhere(plainSelect.getWhere() == null
                    ? extra
                    : new AndExpression(plainSelect.getWhere(), extra));
            PluginUtils.mpBoundSql(boundSql).sql(plainSelect.toString());
        } catch (Exception e) {
            // 解析失败时放行原 SQL（系统内部复杂查询），并记录告警
            log.warn("数据权限拦截器解析 SQL 失败，跳过追加: {}", e.getMessage());
        }
    }
}

package com.demandhub.demand.statemachine;

import com.demandhub.demand.entity.DemandEntity;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Consumer;

/**
 * 一次流转的上下文：操作意见、附加日志信息、领域字段变更钩子。
 * fieldUpdater 由业务层提供（如分派写入处理人、验收写入评分），在引擎校验通过后执行。
 */
public class TransitionContext {

    private String comment;

    private final Map<String, Object> extra = new LinkedHashMap<>();

    private Consumer<DemandEntity> fieldUpdater;

    public static TransitionContext of() {
        return new TransitionContext();
    }

    public static TransitionContext of(String comment) {
        TransitionContext ctx = new TransitionContext();
        ctx.setComment(comment);
        return ctx;
    }

    public TransitionContext withUpdater(Consumer<DemandEntity> updater) {
        this.fieldUpdater = updater;
        return this;
    }

    public TransitionContext putExtra(String key, Object value) {
        this.extra.put(key, value);
        return this;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }

    public Map<String, Object> getExtra() {
        return extra;
    }

    public Consumer<DemandEntity> getFieldUpdater() {
        return fieldUpdater;
    }
}

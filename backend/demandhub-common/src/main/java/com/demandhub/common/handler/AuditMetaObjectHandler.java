package com.demandhub.common.handler;

import com.baomidou.mybatisplus.core.handlers.MetaObjectHandler;
import com.demandhub.common.context.UserContext;
import org.apache.ibatis.reflection.MetaObject;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

/**
 * 公共字段自动填充：created_at/updated_at/created_by/updated_by/is_deleted/version
 * created_by/updated_by 从 UserContext 取当前登录用户，未登录场景（同步 Job 等）为 0
 */
@Component
public class AuditMetaObjectHandler implements MetaObjectHandler {

    @Override
    public void insertFill(MetaObject metaObject) {
        LocalDateTime now = LocalDateTime.now();
        this.strictInsertFill(metaObject, "createdAt", LocalDateTime.class, now);
        this.strictInsertFill(metaObject, "updatedAt", LocalDateTime.class, now);
        this.strictInsertFill(metaObject, "createdBy", Long.class, UserContext.currentUserId());
        this.strictInsertFill(metaObject, "updatedBy", Long.class, UserContext.currentUserId());
        this.strictInsertFill(metaObject, "isDeleted", Integer.class, 0);
        this.strictInsertFill(metaObject, "version", Integer.class, 0);
    }

    @Override
    public void updateFill(MetaObject metaObject) {
        this.strictUpdateFill(metaObject, "updatedAt", LocalDateTime.class, LocalDateTime.now());
        this.strictUpdateFill(metaObject, "updatedBy", Long.class, UserContext.currentUserId());
    }
}

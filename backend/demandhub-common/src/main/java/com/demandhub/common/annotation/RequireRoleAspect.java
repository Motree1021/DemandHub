package com.demandhub.common.annotation;

import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.aspectj.lang.JoinPoint;
import org.springframework.stereotype.Component;

import java.util.Arrays;

/**
 * {@link RequireRole} 切面：未登录返回 401，角色不符返回 403。
 * 注：不使用 @within/@annotation 参数绑定（二者 || 组合时绑定可能为 null），改为反射查找（方法级优先，回退类级）。
 */
@Aspect
@Component
public class RequireRoleAspect {

    @Before("@within(com.demandhub.common.annotation.RequireRole) || @annotation(com.demandhub.common.annotation.RequireRole)")
    public void check(JoinPoint jp) {
        MethodSignature signature = (MethodSignature) jp.getSignature();
        RequireRole requireRole = AnnotatedElementUtils.findMergedAnnotation(signature.getMethod(), RequireRole.class);
        if (requireRole == null) {
            requireRole = AnnotatedElementUtils.findMergedAnnotation(signature.getDeclaringType(), RequireRole.class);
        }
        if (requireRole == null) {
            return;
        }
        if (UserContext.get() == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        // ADMIN 超级用户直通：放行全部业务操作
        if (UserContext.get().isAdmin()) {
            return;
        }
        boolean ok = Arrays.stream(requireRole.value()).anyMatch(UserContext::hasRole);
        if (!ok) {
            throw new BizException(ErrorCode.FORBIDDEN);
        }
    }
}

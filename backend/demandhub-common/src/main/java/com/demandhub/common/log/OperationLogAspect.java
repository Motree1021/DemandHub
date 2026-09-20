package com.demandhub.common.log;

import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.Arrays;

/**
 * 操作日志切面：记录方法、路径、参数、耗时、结果
 * 阶段 2 接入认证后补充操作人字段，阶段 8 落审计日志表
 */
@Slf4j
@Aspect
@Component
public class OperationLogAspect {

    @Around("@annotation(operationLog)")
    public Object around(ProceedingJoinPoint joinPoint, OperationLog operationLog) throws Throwable {
        long start = System.currentTimeMillis();
        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        String method = signature.getDeclaringType().getSimpleName() + "." + signature.getName();

        String uri = "";
        String httpMethod = "";
        ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attrs != null) {
            HttpServletRequest request = attrs.getRequest();
            uri = request.getRequestURI();
            httpMethod = request.getMethod();
        }

        String params = operationLog.logParams() ? Arrays.toString(joinPoint.getArgs()) : "[skipped]";
        log.info("[操作日志] 开始 {} | {} {} | {} | 参数: {}", operationLog.value(), httpMethod, uri, method, params);

        try {
            Object result = joinPoint.proceed();
            log.info("[操作日志] 完成 {} | {} {} | 耗时: {}ms", operationLog.value(), httpMethod, uri,
                    System.currentTimeMillis() - start);
            return result;
        } catch (Throwable e) {
            log.warn("[操作日志] 异常 {} | {} {} | 耗时: {}ms | 异常: {}", operationLog.value(), httpMethod, uri,
                    System.currentTimeMillis() - start, e.getMessage());
            throw e;
        }
    }
}

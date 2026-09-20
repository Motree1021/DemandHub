package com.demandhub.agent.controller;

import com.demandhub.common.core.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 脚手架自检接口：验证服务启动、统一返回体、接口文档
 */
@Tag(name = "自检", description = "脚手架健康检查接口")
@RestController
@RequestMapping("/agent/ping")
public class PingController {

    @Operation(summary = "健康检查")
    @GetMapping
    public Result<Map<String, Object>> ping() {
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("service", "demandhub-agent");
        info.put("status", "UP");
        info.put("time", LocalDateTime.now().toString());
        return Result.ok(info);
    }
}

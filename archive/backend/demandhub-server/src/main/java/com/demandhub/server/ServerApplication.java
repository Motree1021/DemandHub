package com.demandhub.server;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 单体装配入口（H5 Publish 部署形态）：
 * 合并 system/demand/notification/agent 四业务模块，鉴权由本模块 AuthFilter（Servlet 版）承担。
 * 微服务开发形态不受影响（gateway + 四模块独立进程）。
 */
@EnableAsync
@EnableScheduling
@SpringBootApplication(scanBasePackages = {
        "com.demandhub.system",
        "com.demandhub.demand",
        "com.demandhub.notification",
        "com.demandhub.agent",
        "com.demandhub.common",
        "com.demandhub.server"
})
@MapperScan({
        "com.demandhub.system.mapper",
        "com.demandhub.demand.mapper",
        "com.demandhub.notification.mapper",
        "com.demandhub.agent.mapper"
})
public class ServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerApplication.class, args);
    }
}

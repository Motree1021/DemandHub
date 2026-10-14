package com.demandhub.system;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 系统管理与认证权限服务（M1/M8）
 */
@EnableScheduling
@SpringBootApplication(scanBasePackages = {"com.demandhub.system", "com.demandhub.common"})
@MapperScan("com.demandhub.system.mapper")
public class SystemApplication {

    public static void main(String[] args) {
        SpringApplication.run(SystemApplication.class, args);
    }
}

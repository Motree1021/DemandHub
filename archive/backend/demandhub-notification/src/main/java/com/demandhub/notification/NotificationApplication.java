package com.demandhub.notification;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 通知中心服务（M7）
 */
@SpringBootApplication(scanBasePackages = {"com.demandhub.notification", "com.demandhub.common"})
@MapperScan("com.demandhub.notification.mapper")
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}

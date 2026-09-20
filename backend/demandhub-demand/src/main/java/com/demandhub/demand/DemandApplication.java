package com.demandhub.demand;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 需求核心流程服务（M2~M6）
 */
@SpringBootApplication(scanBasePackages = {"com.demandhub.demand", "com.demandhub.common"})
@MapperScan("com.demandhub.demand.mapper")
public class DemandApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemandApplication.class, args);
    }
}

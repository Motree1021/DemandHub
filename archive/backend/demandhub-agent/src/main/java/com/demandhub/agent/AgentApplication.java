package com.demandhub.agent;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * AI Agent 服务（M9）
 */
@SpringBootApplication(scanBasePackages = {"com.demandhub.agent", "com.demandhub.common"})
@MapperScan("com.demandhub.agent.mapper")
public class AgentApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentApplication.class, args);
    }
}

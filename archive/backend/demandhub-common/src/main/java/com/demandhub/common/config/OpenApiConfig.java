package com.demandhub.common.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * OpenAPI / Knife4j 接口文档配置
 * 访问地址：http://localhost:{port}/doc.html
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI demandHubOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("DemandHub 接口文档")
                        .description("创金合信基金零售业务线需求管理系统")
                        .version("v1.0.0")
                        .contact(new Contact().name("财管科技产品部")));
    }
}

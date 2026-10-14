package com.demandhub.common.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;

/**
 * H5 Publish TEST 环境数据源适配：平台 database provision-backend 只经单个 URL 环境变量
 * 下发连接信息（格式 mysql://user:password@host:port/dbname，口令不明文回显），
 * 此处解析为 spring.datasource.* 三要素。本地/compose 注入 MYSQL_HOST 等旧变量时不受影响。
 */
public class DatabaseUrlEnvironmentPostProcessor implements EnvironmentPostProcessor, Ordered {

    private static final String URL_ENV = "DEMANDHUB_DATABASE_URL";

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        String url = environment.getProperty(URL_ENV);
        if (url == null || url.isBlank()) {
            return;
        }
        // 兼容 jdbc:mysql:// 前缀与裸 mysql://
        String normalized = url.startsWith("jdbc:") ? url.substring("jdbc:".length()) : url;
        URI uri = URI.create(normalized);
        String userInfo = uri.getUserInfo();
        if (userInfo == null || !userInfo.contains(":")) {
            throw new IllegalStateException(URL_ENV + " 缺少 user:password 段");
        }
        String[] cred = userInfo.split(":", 2);
        String path = uri.getPath();
        if (path == null || path.length() <= 1) {
            throw new IllegalStateException(URL_ENV + " 缺少数据库名");
        }
        String jdbcUrl = "jdbc:mysql://" + uri.getHost() + ":" + (uri.getPort() > 0 ? uri.getPort() : 3306) + path
                + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true"
                + (uri.getQuery() != null ? "&" + uri.getQuery() : "");

        Map<String, Object> props = new HashMap<>();
        props.put("spring.datasource.url", jdbcUrl);
        props.put("spring.datasource.username", cred[0]);
        props.put("spring.datasource.password", cred[1]);
        environment.getPropertySources().addFirst(new MapPropertySource("demandhubDatabaseUrl", props));
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}

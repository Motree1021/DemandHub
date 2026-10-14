package com.demandhub.demand.config;

import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.demandhub.demand.service.DataScopeService;
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;

/**
 * 将数据权限拦截器挂到公共 MybatisPlusInterceptor 最前（先于分页，保证 count 也带数据范围过滤）
 */
@Configuration
public class DataScopeMybatisConfig {

    private final MybatisPlusInterceptor mybatisPlusInterceptor;
    private final DataScopeService dataScopeService;

    public DataScopeMybatisConfig(MybatisPlusInterceptor mybatisPlusInterceptor,
                                  DataScopeService dataScopeService) {
        this.mybatisPlusInterceptor = mybatisPlusInterceptor;
        this.dataScopeService = dataScopeService;
    }

    @PostConstruct
    public void registerDataScopeInterceptor() {
        // getInterceptors() 返回不可变视图，需重建列表：数据权限置于分页之前，保证 count 也带过滤
        var interceptors = new java.util.ArrayList<>(mybatisPlusInterceptor.getInterceptors());
        interceptors.add(0, new DataScopeInterceptor(dataScopeService));
        mybatisPlusInterceptor.setInterceptors(interceptors);
    }
}

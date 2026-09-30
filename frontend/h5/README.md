# DemandHub H5（Python MVP）

面向创金零售嵌入入口，保留提报、我的需求、需求详情和管理员整理。所有请求统一使用 `/demandhub-api`；生产构建不展示开发登录表单。

## 本地运行与检查

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5174
npm test
npm run typecheck
npm run build
```

开发服务器把 `/demandhub-api` 转发到本机 Python 服务的 8000 端口。开发页面在 `http://127.0.0.1:5174/#/auth`；开发登录还要求后端 `AUTH_DEV_LOGIN=true`。测试用假身份和 Mock 流，不代表真实创金零售或模型服务已验收。

`npm test` 覆盖渠道外层/hash票据清理、管理员路由、Bearer JSON/SSE/文件下载、不完整草稿、来源与revision保护、创建丢包刷新、同页草稿切换、迟到响应隔离、AI请求重试/取消/409、质量清单恢复和动态字段。只有有效 `structured` 与匹配的 `completed done` 同时收到才确认成功；异常输入与未知结果的请求ID保留，明确409改用最新revision和新ID。

## 创金零售参数联调入口

实际已确认的banner使用外层query四参数：`userid`、`X-Auth-Token`、`userName`、`department`。客户端也兼容将完整入口放在hash query，但完整身份只能来自一处。宿主可在外层query或hash query的一处提供 `userid`、`X-Auth-Token`、`userName` 和可选 `department`。参数值需按URL查询规则编码。H5在路由初始化前捕获并立即移除两处的一次性参数，拒绝缺字段、重复、冲突、跨位置混合和同时存在ticket与参数身份的入口；随后只用JSON请求体调用 `POST /demandhub-api/auth/channel-parameters`（`userid/authToken/userName/department`），交换本系统JWT。宿主Token不写入登录store、localStorage、路由对象或错误跳转，后端任意错误原文不进入地址栏。参数、ticket和me响应共享导航generation保护，被后续导航取代的旧请求不能覆盖或清空新账号；JSON接口401只有在请求携带的Bearer仍等于当前JWT时才触发失效。资源加载前的 `no-referrer` 策略禁止后续页面资源请求携带入口Referer。

识别参数不代表已启用登录。后端默认 `CHANNEL_ENTRY_AUTH_MODE=ticket`；只有 `APP_ENV=test`、`CHANNEL_ENTRY_AUTH_MODE=trusted_parameters` 且 `AUTH_DEV_LOGIN=false` 才注册参数交换路由。其他模式返回404，H5显示“参数联调登录尚未开启”，不回退到dev-login，也不凭单独userid登录。单一outer或hash的legacy ticket仍走原SSO交换，这是仓库保留的兼容方案，尚未确认创金零售支持该ticket/verify链路。

目前没有确认宿主Token验证接口；trusted_parameters只是明确受限的测试联调模式，不证明Token真实性，不能据此开放生产。管理员身份由后端白名单决定。客户端处理覆盖地址栏、前端存储和后续请求，不能消除首次页面请求在上游访问日志中的入口参数。

## 打包

使用 h5-package-build 技能，生成本地产物：

```bash
python3 /Users/erik/.agents/skills/h5-package-build/scripts/package_h5.py \
  --source . \
  --build-command "npm run build" \
  --build-dir dist \
  --app-key demandhub \
  --output artifacts/demandhub-h5.zip
```

包根目录为 `index.html`，资源路径相对，使用hash路由。相同zip适用于任意 `/h5/<route-key>/` 与 `/h5-preview/<route-key>/`；API公开前缀固定为服务专属路径。不把环境文件、源码、脚本或密钥打包。此命令只构建和校验，不上传或发布。

## 外部验收

平台静态包与后端、Kong流式代理、真实创金零售SSO/域名白名单、iOS和Android宿主以及真实模型质量与延迟，需要相应环境单独验收。本地Mock或组件测试不代替这些结果。

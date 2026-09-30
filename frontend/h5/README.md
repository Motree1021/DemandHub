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

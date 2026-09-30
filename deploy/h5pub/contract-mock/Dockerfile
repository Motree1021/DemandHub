# DemandHub TEST(H5 Publish) 专用：创金零售 verify 契约 Mock
# 与本地 test 栈同一脚本；APP_KEY/APP_SECRET/PORT 经平台 env 注入
FROM python:3.11-slim
COPY contract_mock_verify.py /app/contract_mock_verify.py
EXPOSE 8099
CMD ["python", "/app/contract_mock_verify.py"]

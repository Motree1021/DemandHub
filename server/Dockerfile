FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
# 管理后台静态产物：本地构建 frontend/admin 后拷入本目录（见 .gitignore），路径与 app/main.py 的 admin_dist 对齐（容器内 /frontend/admin/dist）
COPY frontend/admin/dist /frontend/admin/dist
RUN useradd -r -u 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1} --no-access-log"]

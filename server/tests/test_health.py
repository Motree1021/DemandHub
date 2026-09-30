from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import create_app


async def test_health_and_database_failure(client):
    assert (await client.get("/demandhub-api/health")).json() == {"status": "UP", "db": "UP"}
    class BrokenDatabase:
        async def execute(self, value):
            raise RuntimeError("secret connection URL")
    async def broken_db():
        yield BrokenDatabase()
    app = create_app()
    app.dependency_overrides[get_db] = broken_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/demandhub-api/health")
        assert response.status_code == 503 and "secret" not in response.text


def test_start_command_disables_ticket_access_logs():
    from pathlib import Path
    assert "--no-access-log" in Path("Dockerfile").read_text()
    assert "uv run uvicorn" not in Path("Dockerfile").read_text()


async def test_uncaught_database_error_does_not_log_secrets(caplog):
    from sqlalchemy.exc import OperationalError
    app = create_app()
    @app.get("/demandhub-api/test-error")
    async def fail():
        raise OperationalError("SELECT secret FROM table", {"password": "sensitive-fake-password"}, Exception("mysql://secret-user:secret-password@host/db"))
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.get("/demandhub-api/test-error")
    assert response.json()["code"] == 500
    assert "secret-password" not in response.text + caplog.text
    assert "sensitive-fake-password" not in caplog.text

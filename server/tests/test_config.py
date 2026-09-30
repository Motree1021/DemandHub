import pytest
from pydantic import ValidationError

from app.config import Settings, parse_database_url


@pytest.mark.parametrize("value,password", [
    ("mysql://u:p@localhost/db", "p"), ("jdbc:mysql://u:p@localhost:3308/db?x=1", "p"),
    ("mysql://u:a%40b%2Fc%25@localhost/db", "a@b/c%"), ("mysql://u:a@b/c%@localhost/db", "a@b/c%")])
def test_url_round_trip(value, password):
    url = parse_database_url(value)
    assert url.password == password
    assert url.database == "db"
    assert parse_database_url(url.render_as_string(hide_password=False)).password == password


@pytest.mark.parametrize("value", ["mysql://localhost/db", "mysql://u:p@localhost/", "mysql://u:@localhost/db", "postgres://u:p@localhost/db"])
def test_invalid_url(value):
    with pytest.raises(ValueError):
        parse_database_url(value)


def test_prod_config():
    with pytest.raises(ValidationError):
        Settings(app_env="prod", auth_dev_login=True, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(app_env="test", jwt_secret="short", _env_file=None)

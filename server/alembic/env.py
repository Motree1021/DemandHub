from sqlalchemy import create_engine, pool

from alembic import context
from app.config import get_settings
from app.db.models import Base

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=get_settings().sync_database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(get_settings().sync_database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

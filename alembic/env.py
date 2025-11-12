import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Ensure project root is on sys.path so `core` and `models` can be imported
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import DB settings and metadata from the app
from core.config import settings
from models.base import Base

# Import all model modules so Alembic autogenerate can discover tables
from models import user, account, session, project, asset, verification  # noqa: F401

config = context.config

# Override URL from application settings to avoid duplication
config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)

# Configure logging if sections exist; otherwise skip quietly
try:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
except Exception:
    # Logging config is optional; continue without it
    pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=lambda object, name, type_, reflected, compare_to: not (reflected and not compare_to),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=lambda object, name, type_, reflected, compare_to: not (reflected and not compare_to),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig
import os
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load environment variables from .env
load_dotenv()

config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models for autogenerate
from app.db.base import Base
from app.models import *

target_metadata = Base.metadata


def get_db_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in environment. Check your .env file.")
    return url


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_db_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect column type changes
            compare_server_default=True,  # Detect server default changes
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

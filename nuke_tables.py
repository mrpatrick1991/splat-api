from sqlalchemy import create_engine, text

POSTGRES_BACKEND_URL = "postgresql+psycopg2://postgres:securepassword@localhost:5432/mydatabase"

engine = create_engine(POSTGRES_BACKEND_URL)

reset_tables = """
DROP TABLE IF EXISTS celery_taskmeta CASCADE;
DROP TABLE IF EXISTS celery_tasksetmeta CASCADE;

CREATE TABLE celery_taskmeta (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(155) NOT NULL,
    status VARCHAR(50) NOT NULL,
    result BYTEA,
    date_done TIMESTAMP WITH TIME ZONE NOT NULL,
    traceback TEXT,
    meta BYTEA
);

CREATE TABLE celery_tasksetmeta (
    id SERIAL PRIMARY KEY,
    taskset_id VARCHAR(155) NOT NULL,
    result BYTEA,
    date_done TIMESTAMP WITH TIME ZONE NOT NULL
);
"""

with engine.connect() as connection:
    connection.execute(text(reset_tables))
    print("Celery tables reset successfully.")
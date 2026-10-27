import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Every transaction from this binary identifies its protocol. Old binaries lack
# this marker and are rejected by the migration's database write fence.
from sqlalchemy import event, text
from sqlalchemy.orm import Session

@event.listens_for(Session, 'after_begin')
def whatsapp_protocol_transaction(session, transaction, connection):
    if connection.dialect.name == 'postgresql':
        connection.execute(text("SELECT set_config('integra.whatsapp_protocol','e14b_close_v1',true)"))

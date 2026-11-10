import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ryubee_dev.db")

# Render.com の postgres:// を postgresql:// に変換（SQLAlchemy 2.x対応）
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_kwargs = {}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update({
        "pool_pre_ping": True,     # 切断された古いDB接続を自動検知して再接続
        "pool_recycle": 300,       # 5分ごとに接続をリフレッシュ
        "pool_size": 10,           # 同時接続プール数（事務員複数人の同時作業に対応）
        "max_overflow": 20,        # 一時的な負荷増大時の予備接続数
        "pool_timeout": 15,        # 接続待ちタイムアウト（ハング防止）
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

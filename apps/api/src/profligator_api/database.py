from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from profligator_api.models import Base


class Database:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self._session_factory = sessionmaker(
            bind=self.engine, class_=Session, expire_on_commit=False
        )

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

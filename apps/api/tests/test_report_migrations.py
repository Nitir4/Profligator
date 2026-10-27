from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from profligator_api.database import Database


def test_report_migration_preserves_existing_history_and_matches_models(tmp_path: Path, monkeypatch) -> None:
    from profligator_api.config import get_settings
    from profligator_api.models import Base

    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("PROFLIGATOR_DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "20260925_0003")
        database = Database(url)
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,email,handle,created_at,updated_at) VALUES ('existing','existing@example.com','existing',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO platform_profiles (id,user_id,platform,public_handle,canonical_url,verification_state,connector_mode,created_at,updated_at) VALUES ('profile','existing','leetcode','existing','https://leetcode.com/u/existing','fixture_only','fixture',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO coding_records (id,platform_profile_id,source_id,kind,status,title,canonical_url,topics,source_payload_checksum,created_at,updated_at) VALUES ('record','profile','1','problem','solved','Pair','https://leetcode.com/problems/pair','[]','checksum',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        command.upgrade(config, "head")
        with database.session() as session:
            row = session.execute(text("SELECT role,auth_provider,is_sharing_enabled,share_token FROM users WHERE id='existing'")).one()
            assert tuple(row) == ("candidate", "password", 0, None)
            cluster = session.execute(text("SELECT c.user_id,c.base_problem_title,r.matching_state FROM coding_records r JOIN unique_clusters c ON r.cluster_id=c.id WHERE r.id='record'")).one()
            assert tuple(cluster) == ("existing", "Pair", "missing_statement")
        inspector = inspect(database.engine)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for table in Base.metadata.sorted_tables:
            assert {c["name"] for c in inspector.get_columns(table.name)} == {c.name for c in table.columns}
        command.downgrade(config, "20260925_0003")
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT email FROM users WHERE id='existing'")) == "existing@example.com"
            assert connection.scalar(text("SELECT title FROM coding_records WHERE id='record'")) == "Pair"
        database.dispose()
    finally:
        get_settings.cache_clear()

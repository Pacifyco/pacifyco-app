from sqlalchemy import text


def test_test_database_is_postgres(db_engine):
    with db_engine.connect() as conn:
        version = conn.execute(text("SHOW server_version")).scalar_one()
        db_name = conn.execute(text("SELECT current_database()")).scalar_one()
    assert int(version.split(".")[0]) >= 17
    assert db_name.endswith("_test"), "tests must never run against a non-test database"

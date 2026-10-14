from sqlalchemy.engine import make_url

from core.config import normalize_db_url

HOST = "aws-0-ap-south-1.pooler.supabase.com:5432/postgres"


def test_sqlite_untouched():
    assert normalize_db_url("sqlite:///data/progress.db") == "sqlite:///data/progress.db"


def test_postgres_scheme_uses_psycopg2():
    for scheme in ("postgres", "postgresql"):
        url = normalize_db_url(f"{scheme}://postgres.abc:secret@{HOST}")
        assert url == f"postgresql+psycopg2://postgres.abc:secret@{HOST}"


def test_special_character_password_is_encoded():
    raw = "p@ss:w/rd#1?%"
    url = make_url(normalize_db_url(f"postgresql://postgres.abc:{raw}@{HOST}"))
    assert url.password == raw
    assert url.username == "postgres.abc"
    assert url.host == "aws-0-ap-south-1.pooler.supabase.com" and url.port == 5432


def test_already_encoded_password_not_double_encoded():
    url = make_url(normalize_db_url(f"postgresql://postgres.abc:p%40ss@{HOST}"))
    assert url.password == "p@ss"

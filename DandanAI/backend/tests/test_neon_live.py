"""Live Neon tests. BLOCKED (skipped) until DIRECT_URL is a real Neon connection string. Never faked."""
import os

import pytest

pytestmark = pytest.mark.live_neon
URL = os.environ.get("NEON_TEST_DIRECT_URL", "")


@pytest.mark.skipif(not URL, reason="BLOCKED: set NEON_TEST_DIRECT_URL to a Neon (disposable branch) connection string")
def test_neon_connect_pgvector_and_schema():
    from sqlalchemy import create_engine, text
    from app.database import normalize_pg_url
    eng = create_engine(normalize_pg_url(URL), connect_args={"prepare_threshold": None})
    with eng.connect() as c:
        assert c.execute(text("select 1")).scalar() == 1
        assert c.execute(text("select extname from pg_extension where extname='vector'")).scalar() == "vector"
        assert c.execute(text("select to_regclass('public.legal_chunks')")).scalar() is not None

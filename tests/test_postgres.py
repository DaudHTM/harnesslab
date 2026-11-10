"""Integration against a real PostgreSQL server; each test owns a fresh schema."""
import os
import platform
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from harnesslab.models import HarnessConfig
from harnesslab.runner import work
from harnesslab.store import LostLease, Store
from scripts.bootstrap_demo import bootstrap


@pytest.fixture
def pg_store():
    url = os.environ.get("HARNESSLAB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set HARNESSLAB_TEST_POSTGRES_URL to run real PostgreSQL integration")
    schema = "harnesslab_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["options"] = "-csearch_path=" + schema
    isolated = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    try:
        yield Store(isolated)
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def task():
    return bootstrap(Path(__file__).resolve().parents[1])


def test_postgres_concurrent_claims_and_schema_startup(pg_store):
    with ThreadPoolExecutor(4) as pool:
        assert len(list(pool.map(lambda _: Store(pg_store.url), range(4)))) == 4
    exp = pg_store.experiment("concurrency")
    identities = {pg_store.enqueue(exp, task(), HarnessConfig()) for _ in range(12)}
    with ThreadPoolExecutor(8) as pool:
        claims = list(pool.map(lambda n: pg_store.claim(str(n), experiment=exp), range(12)))
    assert {r["id"] for r in claims} == identities
    assert all(r["attempt"] == 1 for r in claims)
    assert pg_store.claim("extra", experiment=exp) is None


def test_postgres_atomic_budget_and_fencing(pg_store):
    exp = pg_store.experiment("budget", budget_usd=1)
    for _ in range(8):
        pg_store.enqueue(exp, task(), HarnessConfig())
    rows = [pg_store.claim(str(i), experiment=exp) for i in range(8)]
    with ThreadPoolExecutor(8) as pool:
        accepted = list(pool.map(lambda r: pg_store.reserve(r["id"], r["owner"], 1, 0, .3), rows))
    assert accepted.count(True) == 3
    assert pg_store.accounting(exp)["unsettled_reserved_usd"] == pytest.approx(.9)
    stale = rows[0]
    with pg_store.connection(True) as db:
        db.execute("UPDATE runs SET lease=? WHERE id=?", (time.time()-1, stale["id"]))
    replacement = pg_store.claim("new", experiment=exp)
    assert replacement["id"] == stale["id"] and replacement["attempt"] == 2
    assert not pg_store.heartbeat(stale["id"], stale["owner"], 1)
    with pytest.raises(LostLease):
        pg_store.finish(stale["id"], stale["owner"], 1, "solved", {})


def test_postgres_worker_grading_roundtrip(pg_store, tmp_path):
    exp = pg_store.experiment("round trip")
    identity = pg_store.enqueue(exp, task(), HarnessConfig(name="resilient"))
    backend = "macos" if platform.system() == "Darwin" else "local"
    work(pg_store, tmp_path / "artifacts", backend, True, once=True, experiment=exp)
    assert pg_store.get(identity)["status"] == "solved"
    events = pg_store.events(identity)
    assert [e["seq"] for e in events] == list(range(1,len(events)+1))
    assert pg_store.accounting(exp)["unsettled_calls"] == 0

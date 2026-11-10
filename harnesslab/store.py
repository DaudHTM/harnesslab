"""Durable jobs. PostgreSQL in deployment; SQLite for zero-service local demos."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class LostLease(RuntimeError):
    pass


class Store:
    def __init__(self, url=".harnesslab/state.db"):
        self.url = url
        self.postgres = url.startswith(("postgresql://", "postgres://"))
        if not self.postgres:
            Path(url).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if self.postgres:
                db.execute("SELECT pg_advisory_xact_lock(724619804)")
            for sql in [
                "CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, name TEXT NOT NULL, created DOUBLE PRECISION NOT NULL)",
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, task_path TEXT NOT NULL, config TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0, owner TEXT, lease DOUBLE PRECISION, cancelled INTEGER NOT NULL DEFAULT 0, created DOUBLE PRECISION NOT NULL, result TEXT)",
                "CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, seq INTEGER NOT NULL, attempt INTEGER NOT NULL, kind TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run_id,seq))",
                "CREATE INDEX IF NOT EXISTS runs_claim ON runs(status, created)",
                "CREATE TABLE IF NOT EXISTS budgets (experiment_id TEXT PRIMARY KEY, limit_usd DOUBLE PRECISION NOT NULL)",
                "CREATE TABLE IF NOT EXISTS reservations (run_id TEXT NOT NULL, attempt INTEGER NOT NULL, step INTEGER NOT NULL, amount DOUBLE PRECISION NOT NULL, actual DOUBLE PRECISION, PRIMARY KEY(run_id,attempt,step))",
                "CREATE TABLE IF NOT EXISTS study_locks (experiment_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, metadata TEXT NOT NULL)",
            ]:
                db.execute(sql)

    @contextmanager
    def connection(self, write=False):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self.url, row_factory=dict_row) as raw:
                class Adapter:
                    def execute(self, sql, args=()):
                        return raw.execute(sql.replace("?", "%s"), args)
                yield Adapter()
        else:
            raw = sqlite3.connect(self.url, timeout=30)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA journal_mode=WAL")
            try:
                if write:
                    raw.execute("BEGIN IMMEDIATE")
                yield raw
                raw.commit()
            except BaseException:
                raw.rollback()
                raise
            finally:
                raw.close()

    def experiment(self, name, budget_usd=5.0):
        if not 0 < budget_usd <= 1000:
            raise ValueError("experiment budget must be between zero and $1000")
        identity = uuid.uuid4().hex
        with self.connection(True) as db:
            db.execute("INSERT INTO experiments VALUES (?,?,?)", (identity, name, time.time()))
            db.execute("INSERT INTO budgets VALUES (?,?)", (identity, budget_usd))
        return identity

    def reserve(self, identity, owner, attempt, step, amount):
        """Atomically reserve estimated maximum cost across all experiment workers."""
        with self.connection(True) as db:
            lock = " FOR UPDATE" if self.postgres else ""
            row = db.execute("SELECT * FROM runs WHERE id=?" + lock, (identity,)).fetchone()
            if row["owner"] != owner or row["attempt"] != attempt or row["lease"] < time.time():
                raise LostLease(identity)
            budget = db.execute("SELECT * FROM budgets WHERE experiment_id=?" + lock, (row["experiment_id"],)).fetchone()
            if budget is None:
                raise ValueError("legacy experiment lacks a budget; create a new experiment")
            used = db.execute("SELECT COALESCE(SUM(COALESCE(v.actual,v.amount)),0) AS used FROM reservations v JOIN runs r ON r.id=v.run_id WHERE r.experiment_id=?", (row["experiment_id"],)).fetchone()["used"]
            if used + amount > budget["limit_usd"]:
                return False
            db.execute("INSERT INTO reservations VALUES (?,?,?,?,NULL)", (identity, attempt, step, amount))
            return True

    def settle(self, identity, attempt, step, actual):
        with self.connection(True) as db:
            db.execute("UPDATE reservations SET actual=? WHERE run_id=? AND attempt=? AND step=?", (actual, identity, attempt, step))

    def accounting(self, experiment):
        with self.connection() as db:
            rows = db.execute("SELECT v.* FROM reservations v JOIN runs r ON r.id=v.run_id WHERE r.experiment_id=?", (experiment,)).fetchall()
            return {"actual_usd": sum(r["actual"] or 0 for r in rows), "unsettled_reserved_usd": sum(r["amount"] for r in rows if r["actual"] is None), "unsettled_calls": sum(r["actual"] is None for r in rows)}

    def costs_by_run(self, experiment):
        with self.connection() as db:
            rows = db.execute("SELECT v.run_id, COALESCE(SUM(v.actual),0) AS cost FROM reservations v JOIN runs r ON r.id=v.run_id WHERE r.experiment_id=? GROUP BY v.run_id", (experiment,)).fetchall()
            return {r["run_id"]: r["cost"] for r in rows}

    def enqueue(self, experiment, path, config):
        identity = uuid.uuid4().hex
        with self.connection(True) as db:
            db.execute("INSERT INTO runs (id,experiment_id,task_path,config,status,created) VALUES (?,?,?,?,?,?)",
                       (identity, experiment, str(Path(path).resolve()), config.model_dump_json(), "queued", time.time()))
        return identity

    def claim(self, owner, lease_seconds=30, experiment=None):
        now = time.time()
        with self.connection(True) as db:
            scope = " AND experiment_id=?" if experiment else " AND NOT EXISTS (SELECT 1 FROM study_locks sl WHERE sl.experiment_id=runs.experiment_id)"
            scope_args = (experiment,) if experiment else ()
            # Cancelled jobs whose worker died must not remain running forever.
            db.execute("UPDATE runs SET status='cancelled',owner=NULL,lease=NULL WHERE status='running' AND cancelled=1 AND lease<?"+scope, (now,*scope_args))
            db.execute("UPDATE runs SET status='infrastructure_error',result=?,owner=NULL,lease=NULL WHERE status='running' AND cancelled=0 AND attempt>=2 AND lease<?"+scope,
                       (json.dumps({"error": "worker lease expired twice"}), now,*scope_args))
            lock = " FOR UPDATE SKIP LOCKED" if self.postgres else ""
            row = db.execute("SELECT * FROM runs WHERE cancelled=0 AND (status='queued' OR (status='running' AND lease<?))" + scope + " ORDER BY created LIMIT 1" + lock, (now, experiment) if experiment else (now,)).fetchone()
            if not row:
                return None
            row = dict(row)
            if row["status"] == "running":
                seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM events WHERE run_id=?", (row["id"],)).fetchone()["n"]
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (row["id"], seq, row["attempt"], "attempt_interrupted", now,
                           json.dumps({"reason": "worker_lease_expired", "previous_owner": row["owner"]})))
            db.execute("UPDATE runs SET status='running',owner=?,lease=?,attempt=attempt+1 WHERE id=?",
                       (owner, now + lease_seconds, row["id"]))
            row.update(owner=owner, lease=now + lease_seconds, attempt=row["attempt"] + 1, status="running")
            return row

    def lock_study(self, experiment, source_sha256, metadata):
        with self.connection(True) as db:
            db.execute("INSERT INTO study_locks VALUES (?,?,?)", (experiment, source_sha256, json.dumps(metadata)))

    def study_lock(self, experiment):
        with self.connection() as db:
            row = db.execute("SELECT * FROM study_locks WHERE experiment_id=?", (experiment,)).fetchone()
            return dict(row) if row else None

    def heartbeat(self, identity, owner, attempt, seconds=30):
        with self.connection(True) as db:
            # A sleeping host may resume after expiry. Renew only if no replacement
            # has claimed ownership; the atomic owner/generation predicate fences races.
            cur = db.execute("UPDATE runs SET lease=? WHERE id=? AND owner=? AND attempt=? AND status='running'",
                             (time.time() + seconds, identity, owner, attempt))
            return cur.rowcount == 1

    def cancel(self, identity):
        with self.connection(True) as db:
            db.execute("UPDATE runs SET cancelled=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=?", (identity,))

    def get(self, identity):
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (identity,)).fetchone()
            return dict(row) if row else None

    def experiments(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM experiments ORDER BY created DESC").fetchall()]

    def runs(self, experiment=None):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM runs" + (" WHERE experiment_id=?" if experiment else "") + " ORDER BY created", (experiment,) if experiment else ()).fetchall()
            return [dict(r) for r in rows]

    def event(self, identity, attempt, kind, data, owner=None):
        with self.connection(True) as db:
            lock = " FOR UPDATE" if self.postgres else ""
            run = db.execute("SELECT * FROM runs WHERE id=?" + lock, (identity,)).fetchone()
            if owner and (run["owner"] != owner or run["attempt"] != attempt or run["status"] != "running" or run["lease"] < time.time()):
                raise LostLease(identity)
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 AS n FROM events WHERE run_id=?", (identity,)).fetchone()["n"]
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (identity, seq, attempt, kind, time.time(), json.dumps(data)))

    def events(self, identity, after=0):
        with self.connection() as db:
            return [{"schema_version":1, **dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq", (identity, after)).fetchall()]

    def finish(self, identity, owner, attempt, status, result):
        with self.connection(True) as db:
            cur = db.execute("UPDATE runs SET status=?,result=?,owner=NULL,lease=NULL WHERE id=? AND owner=? AND attempt=? AND status='running' AND lease>?",
                             (status, json.dumps(result), identity, owner, attempt, time.time()))
            if cur.rowcount != 1:
                raise LostLease(identity)

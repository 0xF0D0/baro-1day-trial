import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg.types.json import Jsonb

import db
from mappers import MAPPERS
from model import COMMON_COLUMNS, TABLE_COLUMNS, MapError

SOURCE_DATE_DAYS = 3


@dataclass
class Outcome:
    source: str
    brand: str
    run_id: str
    status: str
    result: str  # applied | superseded | empty_no_mapper | no_mapper | failed | already_loaded
    inserted: int = 0
    updated: int = 0
    ended: int = 0
    not_fetched: int = 0
    error: str = ""


def _read_json(path: Path):
    return json.loads(path.read_text())


def discover(collectors_dir: Path) -> list[Path]:
    def sort_key(path: Path):
        try:
            run = _read_json(path)
            return (str(run["source"]), str(run["brand"]), str(run["run_id"]))
        except (OSError, ValueError, KeyError):
            return ("", "", path.name)

    return sorted(Path(collectors_dir).glob("*/raw/*/*.run.json"), key=sort_key)


def _dt(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _read_records(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError("records file missing")
    records = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            raise ValueError(f"{path.name}:{number}: not JSON") from None
    return records


def _insert_run(conn, run: dict, result: str) -> None:
    conn.execute(
        "INSERT INTO runs (source, brand, run_id, started_at, finished_at, status, reason, records, "
        "expected_total, requests, cost_usd, extra, result) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (run["source"], run["brand"], run["run_id"], run["started_at"], run.get("finished_at"),
         run["status"], run["reason"], run.get("records"), run.get("expected_total"), run.get("requests"),
         run.get("cost_usd"), Jsonb(run.get("extra")), result))


def _insert_scope(conn, run: dict, scope, status: str, reason: str) -> None:
    conn.execute("INSERT INTO run_scopes (source, brand, run_id, scope, status, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                 (run["source"], run["brand"], run["run_id"], scope, status, reason))


def _validate(mapper, mapped) -> None:
    for row in mapped.rows:
        if row.table not in TABLE_COLUMNS:
            raise ValueError(f"{row.key}: unknown table {row.table}")
        unknown = [c for c in row.columns if c not in TABLE_COLUMNS[row.table]]
        if unknown:
            raise ValueError(f"{row.key}: unknown column {', '.join(unknown)} for {row.table}")
        if (row.table, row.kind) not in mapper.ENDING:
            raise ValueError(f"{row.key}: no ending policy for ({row.table}, {row.kind})")


def _write_rows(conn, run: dict, mapper, rows) -> tuple[int, int, int]:
    started = _dt(run["started_at"])
    inserted = updated = ended = 0
    latest = {}
    for row in rows:  # the later record wins
        latest[(row.table, row.kind, row.key)] = row
    for row in latest.values():
        policy = mapper.ENDING[(row.table, row.kind)]
        ended_at = None
        if policy == "source_date" and row.columns.get("last_shown_at") is not None:
            shown = _dt(row.columns["last_shown_at"])
            if started - shown > timedelta(days=SOURCE_DATE_DAYS):
                ended_at = shown
        key = (run["source"], run["brand"], row.kind, row.key)
        existing = conn.execute(
            f"SELECT ended_at FROM {row.table} WHERE source = %s AND brand = %s AND kind = %s AND key = %s",
            key).fetchone()
        own = list(row.columns)
        if existing is None:
            names = list(COMMON_COLUMNS) + own
            values = [run["source"], run["brand"], row.kind, row.key, row.scope, row.url, row.fetched_at,
                      run["started_at"], run["started_at"], ended_at, run["run_id"], Jsonb(row.raw)]
            values += [row.columns[c] for c in own]
            conn.execute(f"INSERT INTO {row.table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})",
                         values)
            inserted += 1
        else:
            names = ["scope", "url", "fetched_at", "ended_at", "last_seen_at", "last_run_id", "raw"] + own
            values = [row.scope, row.url, row.fetched_at, ended_at, run["started_at"], run["run_id"],
                      Jsonb(row.raw)] + [row.columns[c] for c in own]
            conn.execute(
                f"UPDATE {row.table} SET {', '.join(n + ' = %s' for n in names)} "
                "WHERE source = %s AND brand = %s AND kind = %s AND key = %s", values + list(key))
            updated += 1
        if ended_at is not None and (existing is None or existing[0] is None):
            ended += 1
    return inserted, updated, ended


def _end_absent(conn, run: dict, mapper, scopes) -> int:
    ok_scopes = [s.name for s in scopes if s.status == "ok"]
    ended = 0
    for (table, kind), policy in mapper.ENDING.items():
        if policy != "absent" or table not in TABLE_COLUMNS:
            continue
        for scope in ok_scopes:
            ended += conn.execute(
                f"UPDATE {table} SET ended_at = %s WHERE source = %s AND brand = %s AND kind = %s AND scope = %s "
                "AND last_run_id <> %s AND ended_at IS NULL",
                (run["started_at"], run["source"], run["brand"], kind, scope, run["run_id"])).rowcount
    return ended


def _load(conn, run_path: Path, mappers: dict, run: dict, out: Outcome) -> Outcome:
    ident = (run["source"], run["brand"], run["run_id"])
    if conn.execute("SELECT 1 FROM runs WHERE source = %s AND brand = %s AND run_id = %s", ident).fetchone():
        out.result = "already_loaded"
        return out
    try:
        records = _read_records(run_path.with_name(run["run_id"] + ".jsonl"))
    except ValueError as e:
        out.result, out.error = "failed", str(e)
        return out
    mapper = mappers.get(run["source"])
    if mapper is None:
        if records:
            out.result = "no_mapper"
            return out
        _insert_run(conn, run, "empty_no_mapper")
        _insert_scope(conn, run, "all", run["status"], run["reason"])
        out.result = "empty_no_mapper"
        return out
    newer = conn.execute("SELECT 1 FROM runs WHERE source = %s AND brand = %s AND result = 'applied' "
                         "AND run_id > %s", ident).fetchone()
    if newer:
        _insert_run(conn, run, "superseded")
        out.result = "superseded"
        return out
    try:
        mapped = mapper.map_run(run, records)
        _validate(mapper, mapped)
    except (MapError, ValueError) as e:
        out.result, out.error = "failed", str(e)
        return out
    _insert_run(conn, run, "applied")
    for scope in mapped.scopes:
        _insert_scope(conn, run, scope.name, scope.status, scope.reason)
    out.inserted, out.updated, out.ended = _write_rows(conn, run, mapper, mapped.rows)
    out.not_fetched = mapped.not_fetched
    out.ended += _end_absent(conn, run, mapper, mapped.scopes)
    out.result = "applied"
    return out


def load_run(conn, run_path: Path, mappers: dict) -> Outcome:
    try:
        run = _read_json(run_path)
        out = Outcome(run["source"], run["brand"], run["run_id"], run["status"], "")
    except Exception as e:
        return Outcome("", "", "", "", "failed", error=f"{run_path.name}: cannot read run result: {e}")
    try:
        _load(conn, run_path, mappers, run, out)
    except Exception as e:  # a bad run is reported, never raised
        conn.rollback()
        out.result, out.error = "failed", str(e)
        return out
    if out.result == "failed":
        conn.rollback()
    else:
        conn.commit()
    return out


def load_all(conn, collectors_dir: Path, mappers: dict) -> list[Outcome]:
    return [load_run(conn, path, mappers) for path in discover(collectors_dir)]


def _without_password(url: str) -> str:
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit(parts._replace(netloc=(parts.username or "") + "@" + host))


def main(argv: list[str] | None = None, mappers: dict | None = None) -> int:
    default_dir = Path(__file__).resolve().parents[2] / "part1" / "collectors"
    parser = argparse.ArgumentParser(description="Load collector run files into Postgres.")
    parser.add_argument("--collectors-dir", type=Path, default=default_dir)
    args = parser.parse_args(argv)
    url = db.database_url()
    try:
        conn = db.connect(url)
    except psycopg.OperationalError as e:
        print(f"cannot connect to {_without_password(url)}: {str(e).strip()}")
        return 1
    try:
        db.ensure_schema(conn)
        outcomes = load_all(conn, args.collectors_dir, MAPPERS if mappers is None else mappers)
    finally:
        conn.close()
    for o in outcomes:
        if o.result == "already_loaded":
            continue
        line = (f"{o.source} {o.brand} {o.run_id} {o.status} {o.result} inserted={o.inserted} "
                f"updated={o.updated} ended={o.ended} not_fetched={o.not_fetched}")
        if o.result == "failed":
            line += f" error={o.error}"
        print(line)
    count = lambda result: sum(1 for o in outcomes if o.result == result)
    no_mapper = ",".join(sorted({o.source for o in outcomes if o.result == "no_mapper"})) or "-"
    print(f"runs: applied={count('applied')} superseded={count('superseded')} "
          f"empty_no_mapper={count('empty_no_mapper')} failed={count('failed')} "
          f"already_loaded={count('already_loaded')} no_mapper={no_mapper}")
    return 1 if count("failed") else 0


if __name__ == "__main__":
    sys.exit(main())

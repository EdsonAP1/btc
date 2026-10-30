"""Persistencia en SQLite: trades, backtests y pares clave-valor."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT,
    side TEXT,
    volume REAL,
    open_time TEXT,
    open_price REAL,
    close_time TEXT,
    close_price REAL,
    sl REAL,
    tp REAL,
    pnl REAL DEFAULT 0,
    commission REAL DEFAULT 0,
    swap REAL DEFAULT 0,
    r_multiple REAL,
    strategy TEXT,
    mode TEXT,
    status TEXT DEFAULT 'open',
    comment TEXT,
    run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_close_time ON trades(close_time);

CREATE TABLE IF NOT EXISTS backtests (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    params TEXT,
    metrics TEXT,
    equity TEXT,
    trades TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ trades
    def add_trade(self, trade: dict[str, Any]) -> int:
        fields = [
            "ticket", "symbol", "side", "volume", "open_time", "open_price",
            "close_time", "close_price", "sl", "tp", "pnl", "commission", "swap",
            "r_multiple", "strategy", "mode", "status", "comment", "run_id",
        ]
        values = [trade.get(f) for f in fields]
        with self._lock:
            cur = self._conn.execute(
                f"INSERT INTO trades ({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
                values,
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def update_trade(self, trade_id: int, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "ticket", "symbol", "side", "volume", "open_time", "open_price",
            "close_time", "close_price", "sl", "tp", "pnl", "commission", "swap",
            "r_multiple", "strategy", "mode", "status", "comment", "run_id",
        }
        clean = {k: v for k, v in fields.items() if k in allowed}
        if not clean:
            return
        assignments = ", ".join(f"{k} = ?" for k in clean)
        with self._lock:
            self._conn.execute(f"UPDATE trades SET {assignments} WHERE id = ?", [*clean.values(), trade_id])
            self._conn.commit()

    def get_trade(self, trade_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None

    def list_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        mode: str | None = None,
        run_id: str | None = None,
    ) -> tuple[int, list[dict]]:
        clauses, args = [], []
        if status:
            clauses.append("status = ?")
            args.append(status)
        if mode:
            clauses.append("mode = ?")
            args.append(mode)
        if run_id:
            clauses.append("run_id = ?")
            args.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            total = self._conn.execute(f"SELECT COUNT(*) FROM trades {where}", args).fetchone()[0]
            rows = self._conn.execute(
                f"SELECT * FROM trades {where} ORDER BY COALESCE(close_time, open_time) DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return int(total), [dict(r) for r in rows]

    def count_trades_since(self, since_iso: str, mode: str | None = None) -> int:
        args: list[Any] = [since_iso]
        where = "WHERE open_time >= ?"
        if mode:
            where += " AND mode = ?"
            args.append(mode)
        with self._lock:
            row = self._conn.execute(f"SELECT COUNT(*) FROM trades {where}", args).fetchone()
        return int(row[0]) if row else 0

    def all_closed_trades(self, mode: str | None = None) -> list[dict]:
        args: list[Any] = []
        where = "WHERE status = 'closed'"
        if mode:
            where += " AND mode = ?"
            args.append(mode)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM trades {where} ORDER BY close_time ASC", args
            ).fetchall()
        return [dict(r) for r in rows]

    def open_trade(self, mode: str | None = None) -> dict | None:
        args: list[Any] = []
        where = "WHERE status = 'open'"
        if mode:
            where += " AND mode = ?"
            args.append(mode)
        with self._lock:
            row = self._conn.execute(
                f"SELECT * FROM trades {where} ORDER BY id DESC LIMIT 1", args
            ).fetchone()
        return dict(row) if row else None

    # --------------------------------------------------------------- backtests
    def save_backtest(self, run: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO backtests (id, created_at, params, metrics, equity, trades, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run["id"],
                    run.get("created_at") or _now(),
                    json.dumps(run.get("params", {})),
                    json.dumps(run.get("metrics", {})),
                    json.dumps(run.get("equity_curve", [])),
                    json.dumps(run.get("trades", [])),
                    run.get("status", "done"),
                ),
            )
            self._conn.commit()

    def get_backtest(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM backtests WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        for key in ("params", "metrics", "equity", "trades"):
            out[key] = json.loads(out[key]) if out[key] else ({} if key in ("params", "metrics") else [])
        out["equity_curve"] = out.pop("equity")
        return out

    def list_backtests(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, created_at, status, params, metrics FROM backtests ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["params"] = json.loads(item["params"]) if item["params"] else {}
            item["metrics"] = json.loads(item["metrics"]) if item["metrics"] else {}
            item.pop("equity", None)
            out.append(item)
        return out

    # ---------------------------------------------------------------------- kv
    def kv_set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def kv_get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

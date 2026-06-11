"""MySQL connection utility for the Nanocare `nano` database.

Provides a thin wrapper around pymysql with connection pooling,
auto-reconnect, and context-manager usage.
"""
import os
import logging
import pymysql
from contextlib import contextmanager

log = logging.getLogger(__name__)


def _get_config() -> dict:
    """Build MySQL config lazily so .env is loaded before we read it."""
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASS", ""),
        "database": os.getenv("MYSQL_DB", "nano"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def _create_connection() -> pymysql.Connection:
    """Create a fresh MySQL connection using env-var config."""
    cfg = _get_config()
    try:
        conn = pymysql.connect(**cfg)
        log.debug(f"MySQL connected: {cfg['host']}:{cfg['port']}/{cfg['database']}")
        return conn
    except pymysql.MySQLError as e:
        log.error(f"MySQL connection failed: {e}")
        raise


# ── Singleton connection (lazy init, auto-reconnect) ─────────────────
_conn: pymysql.Connection | None = None


def get_connection() -> pymysql.Connection:
    """Get or create a MySQL connection. Auto-reconnects if stale."""
    global _conn
    if _conn is None or not _conn.open:
        _conn = _create_connection()
    else:
        try:
            _conn.ping(reconnect=True)
        except pymysql.MySQLError:
            _conn = _create_connection()
    return _conn


@contextmanager
def get_cursor():
    """Context manager yielding a DictCursor with auto-reconnect.

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM ...")
            rows = cur.fetchall()
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def execute_query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """Execute a SELECT query, return all rows as list of dicts."""
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute_write(sql: str, params: tuple | dict | None = None) -> int:
    """Execute an INSERT/UPDATE/DELETE, return affected row count."""
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_many(sql: str, params_list: list[tuple | dict]) -> int:
    """Execute a parameterized statement for multiple rows."""
    with get_cursor() as cur:
        cur.executemany(sql, params_list)
        return cur.rowcount

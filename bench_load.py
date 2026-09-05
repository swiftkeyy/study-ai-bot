"""Микро-бенч узких мест бота (SQLite, event loop, HTTP-сессия).

Ничего не отправляет в Telegram и не трогает AI: измеряет только локальные операции,
которые бот выполняет на каждое сообщение пользователя.

Запуск:
    BOT_TOKEN=x ADMIN_ID=1 DATA_DIR=/tmp/bench python bench_load.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import threading
import time

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("ADMIN_ID", "1")

import aiohttp

import bot  # импортируем, чтобы заодно проверить, что модуль собирается с новым config
import config
import db as db_module


class CountingConn:
    """Прозрачная обёртка sqlite-соединения: считает statements и выполняет их по-настоящему."""

    def __init__(self, conn, counter):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_counter", counter)

    def execute(self, sql, parameters=()):
        self._counter["statements"] += 1
        return self._conn.execute(sql, parameters)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._conn.__exit__(exc_type, exc, tb)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)


def instrument(counter: dict) -> callable:
    """Подменяет Database._connect, чтобы посчитать соединения/запросы одного запроса."""
    real = db_module.Database._connect

    def counting_connect(self):
        counter["connections"] += 1
        return CountingConn(real(self), counter)

    db_module.Database._connect = counting_connect
    return real


db = db_module.Database(config.DB_PATH)
loop = asyncio.new_event_loop()


def run(coro):
    return loop.run_until_complete(coro)


def one_user_request(db, uid: int, username: str) -> None:
    """Ровно те обращения к БД, которые бот делает на одно текстовое сообщение."""
    db.get_or_create_user(uid, username)
    db.refresh_subscription_status(uid)
    db.is_maintenance_enabled()
    db.is_feature_enabled("solve")
    db.has_access(uid)
    db.decrement_request_if_needed(uid)
    db.get_ai_settings()
    db.add_request_log(uid, "solve", "gemini")
    db.get_user(uid)
    db.get_stats()


def request_path_benchmark(n_cycles: int = 50) -> dict:
    counter = {"connections": 0, "statements": 0}
    real = instrument(counter)
    users = [db.get_or_create_user(i, f"u{i}")["id"] for i in range(1, 6)]
    try:
        t0 = time.perf_counter()
        for _ in range(n_cycles):
            for uid in users:
                one_user_request(db, uid, f"u{uid}")
        elapsed = time.perf_counter() - t0
    finally:
        db_module.Database._connect = real

    per_cycle = elapsed / n_cycles
    return {
        "cycles": n_cycles,
        "users_per_cycle": len(users),
        "sqlite_connections_per_request": round(counter["connections"] / n_cycles / len(users), 1),
        "sqlite_statements_per_request": round(counter["statements"] / n_cycles / len(users), 1),
        "ms_per_request": round(per_cycle * 1000 / len(users), 2),
    }


def loop_block_benchmark(n_cycles: int = 50) -> dict:
    """Насколько синхронный sqlite блокирует event loop бота."""
    users = [db.get_or_create_user(i, f"u{i}")["id"] for i in range(1, 6)]
    delays: list[float] = []

    async def main():
        stop = asyncio.Event()

        async def heartbeat():
            while not stop.is_set():
                t0 = time.perf_counter()
                await asyncio.sleep(0.001)
                delays.append((time.perf_counter() - t0 - 0.001) * 1000)

        hb = asyncio.create_task(heartbeat())
        t0 = time.perf_counter()
        for _ in range(n_cycles):
            for uid in users:
                # как в хендлерах: вызовы синхронные, loop ждёт их завершения
                one_user_request(db, uid, f"u{uid}")
                await asyncio.sleep(0)
        total_ms = (time.perf_counter() - t0) * 1000
        stop.set()
        await asyncio.sleep(0.02)
        hb.cancel()
        return total_ms

    total_ms = run(main())
    return {
        "total_ms": round(total_ms, 1),
        "ms_per_user_request": round(total_ms / (n_cycles * len(users)), 2),
        "max_heartbeat_lag_ms": round(max(delays), 2) if delays else 0.0,
        "p99_heartbeat_lag_ms": round(statistics.quantiles(delays, n=100)[98], 2)
        if len(delays) > 10
        else 0.0,
    }


def write_contention_benchmark(threads: int = 8, ops_per_thread: int = 200) -> dict:
    """Пишет из нескольких потоков в одну базу (эмуляция параллельных запросов)."""
    import sqlite3

    def worker(idx: int, latencies: list[float], errors: list[str]):
        conn = sqlite3.connect(config.DB_PATH, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            for i in range(ops_per_thread):
                t0 = time.perf_counter()
                conn.execute(
                    "UPDATE users SET requests_left = requests_left + 1, "
                    "last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (1 + ((idx * ops_per_thread + i) % 400),),
                )
                conn.commit()
                latencies.append((time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()

    def timed_worker(idx):
        local: list[float] = []
        errs: list[str] = []
        worker(idx, local, errs)
        with lock:
            latencies.extend(local)
            errors.extend(errs)

    t0 = time.perf_counter()
    ts = [threading.Thread(target=timed_worker, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wall = time.perf_counter() - t0

    ordered = sorted(latencies)
    return {
        "threads": threads,
        "ops": len(latencies),
        "wall_s": wall,
        "ops_per_s": len(latencies) / wall if wall else 0,
        "p50_ms": ordered[len(ordered) // 2] if ordered else 0.0,
        "p99_ms": ordered[int(len(ordered) * 0.99) - 1] if ordered else 0.0,
        "max_ms": ordered[-1] if ordered else 0.0,
        "errors": len(errors),
        "first_error": errors[0] if errors else "",
    }


def session_cost_benchmark(n: int = 200) -> float:
    async def main():
        t0 = time.perf_counter()
        for _ in range(n):
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.AI_CONNECTION_TIMEOUT))
            await session.close()
        return (time.perf_counter() - t0) / n * 1000

    return run(main())


def main() -> None:
    print(
        f"limits: concurrent updates={bot.MAX_CONCURRENT_UPDATES}, "
        f"ai connections={config.AI_CONNECTION_LIMIT}, "
        f"message limit={bot.TELEGRAM_MESSAGE_LIMIT}, log rotate={config.LOG_MAX_BYTES}B"
    )
    for i in range(1, 401):
        db.get_or_create_user(i, f"bench{i}")

    path = request_path_benchmark()
    print(f"db work per user request: {path}")
    blocked = loop_block_benchmark()
    print(f"event loop blocking: {blocked}")
    print(f"write contention: {write_contention_benchmark()}")
    print(f"per-request aiohttp session create+close: {session_cost_benchmark():.3f} ms")


if __name__ == "__main__":
    main()
    loop.close()

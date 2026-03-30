import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/app/data/bot.db")
DEFAULT_FREE_LIMIT = int(os.getenv("DEFAULT_FREE_LIMIT", "3"))

def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}

def main() -> None:
    print(f"Using DB: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("ERROR: database file not found")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # users: снять бан
    user_cols = table_columns(conn, "users")
    if "is_banned" in user_cols:
        if "ban_reason" in user_cols:
            cur.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE is_banned != 0"
            )
        else:
            cur.execute("UPDATE users SET is_banned = 0 WHERE is_banned != 0")
        print(f"users unbanned: {cur.rowcount}")
    else:
        print("skip users ban reset: no is_banned column")

    # users: вернуть бесплатные лимиты обычным пользователям
    if {"requests_left", "is_premium", "is_vip"}.issubset(user_cols):
        cur.execute(
            """
            UPDATE users
            SET requests_left = ?
            WHERE (requests_left IS NULL OR requests_left <= 0)
              AND COALESCE(is_premium, 0) = 0
              AND COALESCE(is_vip, 0) = 0
            """,
            (DEFAULT_FREE_LIMIT,),
        )
        print(f"users free limits restored: {cur.rowcount}")
    else:
        print("skip requests_left reset: missing columns")

    # settings: выключить техработы и обязательную подписку
    settings_cols = table_columns(conn, "settings")
    if settings_cols:
        if "maintenance_enabled" in settings_cols:
            cur.execute("UPDATE settings SET maintenance_enabled = 0")
            print(f"settings maintenance disabled: {cur.rowcount}")
        else:
            print("skip maintenance_enabled: no column")

        if "required_subscription_enabled" in settings_cols:
            cur.execute("UPDATE settings SET required_subscription_enabled = 0")
            print(f"settings required subscription disabled: {cur.rowcount}")
        else:
            print("skip required_subscription_enabled: no column")
    else:
        print("skip settings updates: table empty or missing")

    conn.commit()

    # Небольшая сводка
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN COALESCE(is_banned, 0) != 0 THEN 1 ELSE 0 END) AS banned_users
            FROM users
            """
        ).fetchone()
        if row:
            print(f"total_users={row['total_users']}, banned_users={row['banned_users']}")
    except Exception:
        pass

    conn.close()
    print("done")

if __name__ == "__main__":
    main()

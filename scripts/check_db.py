from pathlib import Path
import sqlite3

db_path = Path("arbitrage_bot.db").resolve()
print("DB path opened by check_db.py:", db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("Tables:")
print(cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())

for table in [
    "heartbeat",
    "market_snapshots",
    "funding_snapshots",
    "funding_opportunities",
    "execution_results",
    "position_pairs",
]:
    try:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count}")
    except Exception as exc:
        print(f"{table}: ERROR -> {exc}")

conn.close()
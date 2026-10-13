import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def db_path():
    path = Path(os.getenv("STOCK_DB_PATH", "data/stock-panel.sqlite3"))
    return path if path.is_absolute() else ROOT / path


def token():
    return os.getenv("TUSHARE_TOKEN", "").strip()


def data_provider():
    value = os.getenv("DATA_PROVIDER", "free").strip().lower()
    if value not in {"free", "tushare"}:
        raise ValueError("DATA_PROVIDER 只能为 free 或 tushare")
    return value

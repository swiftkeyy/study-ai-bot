"""Shared test setup.

App modules read configuration at import time, so the environment has to be
prepared before anything is imported from the project root.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BOT_TOKEN"] = "123456:test-token"
os.environ["ADMIN_ID"] = "1"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="study-ai-tests-")
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["GROQ_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["MISTRAL_API_KEY"] = ""
os.environ["DEEPAI_API_KEY"] = ""
os.environ["BOT_USERNAME"] = ""
os.environ["DEFAULT_FREE_LIMIT"] = "3"
os.environ["DEFAULT_REFERRAL_BONUS"] = "5"
os.environ["ROBOKASSA_MERCHANT_LOGIN"] = "test-merchant"
os.environ["ROBOKASSA_PASSWORD1"] = "test-password-1"
os.environ["ROBOKASSA_PASSWORD2"] = "test-password-2"
os.environ["ROBOKASSA_HASH_ALGO"] = "md5"
os.environ["ROBOKASSA_IS_TEST"] = "1"
os.environ["ROBOKASSA_PUBLIC_BASE_URL"] = ""
os.environ["ROBOKASSA_RECEIPT_ENABLED"] = "1"
os.environ["ROBOKASSA_DEBUG_SIGNATURE"] = "0"

from db import Database  # noqa: E402


@pytest.fixture()
def db(tmp_path: pathlib.Path) -> Database:
    """A fresh database per test."""
    return Database(str(tmp_path / "test.db"))

"""One throwaway SQLite DB per pytest run. Must be set before app.database is imported."""
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="flowjai_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
os.environ["FLOWJAI_UPLOAD_DIR"] = str(Path(_TMP, "uploads"))

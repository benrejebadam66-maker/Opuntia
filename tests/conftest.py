import os
import shutil
import tempfile
import uuid
from pathlib import Path


def pytest_configure():
    """
    Force test temp files into a writable folder inside the repository.

    Some environments deny access to the default Windows TEMP path, which
    breaks tests relying on tempfile.TemporaryDirectory/mkdtemp.
    """
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / ".tmp_test_runtime"
    tmp_root.mkdir(parents=True, exist_ok=True)

    tmp_str = str(tmp_root)
    os.environ["TMP"] = tmp_str
    os.environ["TEMP"] = tmp_str
    tempfile.tempdir = None

    def _safe_mkdtemp(suffix=None, prefix=None, dir=None):
        base = Path(dir or tmp_str)
        base.mkdir(parents=True, exist_ok=True)
        name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
        path = base / name
        path.mkdir(parents=True, exist_ok=False)
        return str(path)

    class _SafeTemporaryDirectory:
        def __init__(self, suffix=None, prefix=None, dir=None):
            self.name = _safe_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
            self._closed = False

        def cleanup(self):
            if self._closed:
                return
            shutil.rmtree(self.name, ignore_errors=True)
            self._closed = True

        def __enter__(self):
            return self.name

        def __exit__(self, exc, value, tb):
            self.cleanup()

    tempfile.mkdtemp = _safe_mkdtemp
    tempfile.TemporaryDirectory = _SafeTemporaryDirectory

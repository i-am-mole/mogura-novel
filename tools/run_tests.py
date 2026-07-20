from pathlib import Path
import os
import sys
import tempfile
import unittest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tools = root / "tools"
    temp_root = root / ".novel-editor" / "test-tmp"
    pycache = root / ".novel-editor" / "pycache"
    temp_root.mkdir(parents=True, exist_ok=True)
    pycache.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(temp_root)
    os.environ["TMP"] = str(temp_root)
    os.environ["PYTHONPYCACHEPREFIX"] = str(pycache)
    sys.pycache_prefix = str(pycache)
    tempfile.tempdir = str(temp_root)
    sys.path.insert(0, str(tools))
    suite = unittest.defaultTestLoader.discover(str(tools), pattern="test*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

# core/paths.py
from pathlib import Path

# 项目根目录（zhiwei/）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 常用目录
TEST_DIR = PROJECT_ROOT / "test"
DOCS_DIR = TEST_DIR / "docs"
TEMP_DIR = TEST_DIR / "temp_dir"
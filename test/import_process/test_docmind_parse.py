#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DocMind 文档解析连通性测试

用真实 PDF 走一遍 DocMind POP 通道 -> Markdown，验证：
  1. 凭证可用（DOCMIND_ACCESS_KEY_ID / SECRET）
  2. 异步任务提交/轮询/结果拉取链路正常
  3. Markdown 结果能正确拼接

用法：
    # 1) 在 .env 填好 DOCMIND_ACCESS_KEY_ID / DOCMIND_ACCESS_KEY_SECRET
    # 2) 运行：
    python test/import_process/test_docmind_parse.py
    # 或指定文件：
    python test/import_process/test_docmind_parse.py /path/to/other.pdf

输出：
    test/temp_dir/<原文件名>.md
"""
import sys
from pathlib import Path

# 允许直接以脚本方式运行，把项目根加到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from core.paths import DOCS_DIR, TEMP_DIR  # noqa: E402
from processor.import_process.config import get_config  # noqa: E402
from utils.client.docmind_client import DocMindClient  # noqa: E402


def main(pdf_path: Path) -> int:
    cfg = get_config()

    print("=" * 60)
    print("DocMind 解析连通性测试")
    print("=" * 60)

    # --- 前置校验 ---
    if not cfg.docmind_access_key_id or not cfg.docmind_access_key_secret:
        print("✗ 缺少凭证：请在 .env 中配置 DOCMIND_ACCESS_KEY_ID / DOCMIND_ACCESS_KEY_SECRET")
        return 2
    if not pdf_path.exists():
        print(f"✗ 待解析文件不存在: {pdf_path}")
        return 2

    print(f"endpoint        : {cfg.docmind_endpoint}")
    print(f"enhancement     : {cfg.docmind_enhancement_mode}  (llm={cfg.docmind_llm_enhancement})")
    print(f"poll/timeout    : {cfg.docmind_poll_interval}s / {cfg.docmind_timeout}s")
    print(f"input file      : {pdf_path}  ({pdf_path.stat().st_size} bytes)")

    # --- 执行解析 ---
    client = DocMindClient(
        enhancement_mode=cfg.docmind_enhancement_mode,
        llm_enhancement=cfg.docmind_llm_enhancement,
        poll_interval=cfg.docmind_poll_interval,
        timeout=cfg.docmind_timeout,
        layout_step_size=cfg.docmind_layout_step_size,
    )

    print("\n>>> 开始解析（提交 -> 轮询 -> 拉取）...")
    try:
        markdown = client.parse_to_markdown(pdf_path)
    except Exception as e:
        print(f"✗ 解析失败: {type(e).__name__}: {e}")
        return 1

    # --- 输出结果 ---
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TEMP_DIR / f"{pdf_path.stem}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print(f"\n✓ 解析成功，markdown 长度 = {len(markdown)}")
    print(f"✓ 已写入: {out_path}")
    print("\n--- Markdown 前 500 字预览 ---")
    print(markdown[:500])
    print("--- 预览结束 ---")
    return 0


if __name__ == "__main__":
    default_pdf = DOCS_DIR / "H3C-LA2608.pdf"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default_pdf
    sys.exit(main(target))

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回归测试统一跑批入口（纯标准库 unittest，无需 pytest）

设计：
- 自动扫描 test/ 下所有 test_*.py，导入后仅收集 unittest.TestCase 用例并运行。
- 项目内网络型脚本（如 test_connections.py 的 test_milvus()/test_mongodb() 等函数、
  test_docmind_parse.py 的 main()）不是 TestCase，因此**不会被本入口触发**，
  回归运行全程离线、不触网。这些脚本仍按各自说明单独 `python xxx.py` 执行。
- 单个测试文件导入失败不影响整体，会记录为加载错误并在结尾提示。

用法：
    python test/run_tests.py                 # 运行全部离线回归用例
    python test/run_tests.py subject         # 只运行文件名含 "subject" 的测试
"""
import importlib.util
import sys
import unittest
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _import_module_from_path(file_path: Path):
    """按文件路径导入模块（规避 test 目录无 __init__.py 的包导入问题）。"""
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(name_filter: str = ""):
    """收集 TestCase 用例；name_filter 非空时仅匹配文件名包含该串的测试文件。"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    loaded, load_errors = [], []

    for file_path in sorted(TEST_ROOT.rglob("test_*.py")):
        if file_path.name == Path(__file__).name:
            continue
        if name_filter and name_filter not in file_path.name:
            continue
        try:
            module = _import_module_from_path(file_path)
        except Exception as exc:  # 导入失败不阻断整体
            load_errors.append((file_path.relative_to(PROJECT_ROOT), exc))
            continue
        module_suite = loader.loadTestsFromModule(module)
        if module_suite.countTestCases() > 0:
            suite.addTests(module_suite)
            loaded.append((file_path.relative_to(PROJECT_ROOT), module_suite.countTestCases()))
        else:
            # 无 TestCase（多为网络型脚本），跳过但记录，便于确认未被误跑
            load_errors.append((file_path.relative_to(PROJECT_ROOT), None))

    return suite, loaded, load_errors


def main() -> int:
    name_filter = sys.argv[1] if len(sys.argv) > 1 else ""
    suite, loaded, skipped = collect(name_filter)

    print("=" * 60)
    print("离线回归测试运行")
    if name_filter:
        print(f"文件名过滤: *{name_filter}*")
    print("=" * 60)

    for rel, count in loaded:
        print(f"  [收集] {rel} -> {count} 用例")
    for rel, exc in skipped:
        if exc is None:
            print(f"  [跳过] {rel}（无 TestCase，需单独运行）")
        else:
            print(f"  [错误] {rel} 导入失败: {type(exc).__name__}: {exc}")

    if suite.countTestCases() == 0:
        print("\n未收集到任何 TestCase 用例。")
        return 1

    print(f"\n共 {suite.countTestCases()} 个用例，开始运行...\n")
    sys.stdout.flush()
    # 统一输出到 stdout，避免与上方信息因缓冲乱序
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)

    ok = result.wasSuccessful()
    print("\n" + "=" * 60)
    print(f"结果: 运行 {result.testsRun}"
          f" | 失败 {len(result.failures)} | 错误 {len(result.errors)}"
          f" | {'通过 ✓' if ok else '失败 ✗'}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

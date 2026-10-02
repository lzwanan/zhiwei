#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
md_img 节点端到端集成测试

在隔离临时目录中构造真实 MD + images/ 图片，跑通 MdImgNode 全流程（非 mock）：
  1. MdFileHandler 读取 MD、定位 images 目录
  2. ImageScanner 提取图片上下文
  3. VLMSummarizer  -> 阿里百炼 VLM 生成中文标题
  4. ImageUploader  -> 阿里云 OSS 上传并替换 MD 引用
  5. MdFileHandler 备份 _new 文件

校验：
  - 输出的 md_content 含 OSS 远程 URL 与生成的摘要
  - 生成 *_new.md 备份文件
  - OSS 上真实存在对应对象（随后清理）

用法：
    python test/import_process/test_md_img_e2e.py
"""
import logging
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from processor.import_process.config import get_config  # noqa: E402
from processor.import_process.nodes.md_img import MdImgNode  # noqa: E402
from processor.import_process.nodes.pdf_to_md import _IMAGE_DIR_NAME  # noqa: E402
from processor.import_process.state import create_default_state  # noqa: E402
from utils.client.storage_clients import StorageClients  # noqa: E402

# 复用已存在的样张作为待处理图片
SRC_IMAGE = PROJECT_ROOT / "test" / "temp_dir" / "image" / "001_3.png"
# 隔离临时工作区（测试后清理）
WORKSPACE = PROJECT_ROOT / "test" / "temp_dir" / "md_img_e2e"


def _build_workspace() -> Path:
    """构造 <workspace>/doc.md + <workspace>/image/001_3.png。"""
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    images_dir = WORKSPACE / _IMAGE_DIR_NAME
    images_dir.mkdir(parents=True)
    shutil.copy2(SRC_IMAGE, images_dir / SRC_IMAGE.name)

    md_text = (
        "# 1.2 配置LA2608与无线控制器互通\n\n"
        "如图1所示，LA2608安装了SIM卡，通过 3G/4G网络连接到运营商无线控制器。\n\n"
        f"![b48a9c4e]({_IMAGE_DIR_NAME}/{SRC_IMAGE.name})\n\n"
        "配置LA2608与无线控制器互通的网络拓扑。\n"
    )
    md_path = WORKSPACE / "doc.md"
    md_path.write_text(md_text, encoding="utf-8")
    return md_path


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = get_config()

    print("=" * 60)
    print("md_img 端到端集成测试（MdImgNode 全流程）")
    print("=" * 60)

    if not SRC_IMAGE.exists():
        print(f"✗ 样例图片不存在: {SRC_IMAGE}")
        return 2

    md_path = _build_workspace()
    object_name = f"{md_path.stem}/{SRC_IMAGE.name}"
    oss_url = f"{cfg.get_oss_base_url()}/{object_name}"

    try:
        node = MdImgNode()
        state = create_default_state(md_path=str(md_path))

        print(f"\n>>> 输入 MD: {md_path}")
        print(f">>> 预期 OSS 对象: {object_name}")
        result = node(state)

        new_content = result.get("md_content", "")
        print("\n--- 处理后 MD 内容 ---")
        print(new_content.strip())
        print("--- 结束 ---\n")

        backup_path = md_path.with_name(f"{md_path.stem}_new{md_path.suffix}")

        checks = {
            "md_content 含 OSS 远程 URL": oss_url in new_content,
            "本地相对路径已被替换": f"{_IMAGE_DIR_NAME}/{SRC_IMAGE.name}" not in new_content,
            "生成 *_new.md 备份文件": backup_path.exists(),
        }

        # 校验 OSS 对象真实存在
        try:
            bucket = StorageClients.get_oss_client()
            checks["OSS 对象真实存在"] = bucket.object_exists(object_name)
        except Exception as e:
            print(f"✗ OSS 校验失败: {type(e).__name__}: {e}")
            checks["OSS 对象真实存在"] = False

        all_ok = all(checks.values())
        print("校验结果:")
        for name, ok in checks.items():
            print(f"  {'✓' if ok else '✗'} {name}")

        return 0 if all_ok else 1
    finally:
        # 清理：OSS 对象 + 临时工作区
        try:
            StorageClients.get_oss_client().delete_object(object_name)
            print(f"\n✓ 已清理 OSS 对象: {object_name}")
        except Exception as e:
            print(f"\n! 清理 OSS 对象失败: {e}")
        if WORKSPACE.exists():
            shutil.rmtree(WORKSPACE)
            print(f"✓ 已清理临时工作区: {WORKSPACE}")


if __name__ == "__main__":
    sys.exit(main())

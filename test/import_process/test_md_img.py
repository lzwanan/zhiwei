#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
md_img 节点重构功能性测试

针对重构后的两个协作类做真实链路验证（非 mock）：
  1. VLMSummarizer  -> 阿里百炼视觉模型（VL_MODEL，DashScope 兼容模式）生成中文标题
  2. ImageUploader  -> 阿里云 OSS 上传图片，并把 MD 图片引用替换为远程 URL + 摘要

用法：
    # 1) 在 .env 配好 DASHSCOPE_API_KEY / OPENAI_API_BASE / VL_MODEL 与 OSS_* 
    # 2) 运行：
    python test/import_process/test_md_img.py
"""
import logging
import sys
from pathlib import Path

# 允许直接以脚本方式运行，把项目根加到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from processor.import_process.config import get_config  # noqa: E402
from processor.import_process.nodes.md_img import (  # noqa: E402
    ImageInfo,
    ImageContext,
    VLMSummarizer,
    ImageUploader,
)
from utils.client.storage_clients import StorageClients  # noqa: E402

# 测试用真实图片与节点名称
IMAGE_PATH = PROJECT_ROOT / "test" / "temp_dir" / "image" / "001_3.png"
NODE_NAME = "md_img_node"


def _build_image_info() -> ImageInfo:
    """构造一张图片的完整信息（含 MD 上下文）。"""
    return ImageInfo(
        name=IMAGE_PATH.name,
        path=str(IMAGE_PATH),
        context=ImageContext(
            heading="# 1.2 配置LA2608与无线控制器互通",
            pre_text="如图1所示，LA2608安装了SIM卡，通过3G/4G网络连接到运营商无线控制器。",
            post_text="配置LA2608与无线控制器互通的网络拓扑。",
        ),
    )


def test_vlm_summarizer(cfg) -> bool:
    """验证 VLMSummarizer 能通过阿里百炼 VLM 生成中文摘要。"""
    print("\n" + "=" * 60)
    print("[1] VLMSummarizer —— 阿里百炼 VLM 摘要生成")
    print("=" * 60)
    print(f"vl_model : {cfg.vl_model}")
    print(f"api_base : {cfg.openai_api_base}")

    logger = logging.getLogger("test.vlm")
    summarizer = VLMSummarizer(logger, NODE_NAME)
    image_list = [_build_image_info()]

    summaries = summarizer.summarize_all(
        document_title="H3C LA2608室内无线网关用户手册",
        image_list=image_list,
        vl_model=cfg.vl_model,
        requests_per_minute=cfg.requests_per_minute,
    )

    summary = summaries.get(IMAGE_PATH.name, "")
    print(f"生成摘要 : {summary!r}")

    # 回退默认值说明模型不可用或调用失败
    degraded = summary in ("", "图片描述", "暂无图片")
    if degraded:
        print("✗ 未得到模型生成的有效摘要（可能凭证/网络/模型不可用）")
        return False
    print("✓ VLM 摘要生成成功")
    return True


def test_image_uploader(cfg) -> bool:
    """验证 ImageUploader 能上传到阿里云 OSS 并替换 MD 引用。"""
    print("\n" + "=" * 60)
    print("[2] ImageUploader —— 阿里云 OSS 上传 + MD 替换")
    print("=" * 60)
    print(f"bucket    : {cfg.oss_bucket}")
    print(f"oss_base  : {cfg.get_oss_base_url()}")

    logger = logging.getLogger("test.upload")
    uploader = ImageUploader(logger, NODE_NAME)

    img = _build_image_info()
    document_name = "test_md_img_func"
    object_name = f"{document_name}/{img.name}"
    summaries = {img.name: "无线控制器组网示意图"}
    md_content = f"参考下图：\n\n![b48a9c4e]({img.name})\n"

    new_md = uploader.upload_and_replace(
        document_name=document_name,
        md_content=md_content,
        images_summaries=summaries,
        image_list=[img],
        oss_base_url=cfg.get_oss_base_url(),
    )
    print("替换后 MD:")
    print(new_md.strip())

    expected_url = f"{cfg.get_oss_base_url()}/{object_name}"
    replaced = expected_url in new_md and "无线控制器组网示意图" in new_md

    # 校验对象是否真实存在于 OSS
    oss_exists = False
    try:
        bucket = StorageClients.get_oss_client()
        oss_exists = bucket.object_exists(object_name)
    except Exception as e:
        print(f"✗ OSS 连接/校验失败: {type(e).__name__}: {e}")

    # 清理测试上传的对象
    if oss_exists:
        try:
            bucket.delete_object(object_name)
            print(f"✓ 已清理测试对象: {object_name}")
        except Exception as e:
            print(f"! 清理测试对象失败: {e}")

    if replaced and oss_exists:
        print("✓ OSS 上传成功且 MD 引用已替换为远程 URL + 摘要")
        return True

    if not oss_exists:
        print("✗ OSS 中未查到上传对象（可能凭证/网络/桶配置不可用）")
    if not replaced:
        print("✗ MD 未替换为预期的远程 URL + 摘要")
    return False


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = get_config()

    print("=" * 60)
    print("md_img 重构功能性测试（阿里 VLM + 阿里云 OSS）")
    print("=" * 60)

    if not IMAGE_PATH.exists():
        print(f"✗ 测试图片不存在: {IMAGE_PATH}")
        return 2

    r1 = test_vlm_summarizer(cfg)
    r2 = test_image_uploader(cfg)

    print("\n" + "=" * 60)
    print("结果汇总")
    print("=" * 60)
    print(f"  VLMSummarizer : {'✓ 通过' if r1 else '✗ 失败'}")
    print(f"  ImageUploader : {'✓ 通过' if r2 else '✗ 失败'}")

    return 0 if (r1 and r2) else 1


if __name__ == "__main__":
    sys.exit(main())

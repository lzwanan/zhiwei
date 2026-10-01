"""
PDF 转 Markdown 节点

使用 DocMind 将 PDF 文档转换为 Markdown 格式。
DocMind 返回的 Markdown 里图片是带签名的临时在线外链（会过期），
本节点在落盘前把这些图片下载到 Markdown 同级的 image 目录，改写为本地相对路径。
"""
import re
from pathlib import Path
from typing import Tuple
from urllib.parse import unquote, urlsplit

import requests

from processor.import_process.base import BaseNode
from processor.import_process.exceptions import ValidationError, FileProcessingError
from processor.import_process.state import ImportGraphState
from utils.client.docmind_client import DocMindClient

# Markdown 图片语法：![alt](url "可选title")，只抓取 http/https 在线外链
_IMAGE_PATTERN = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\(\s*(?P<url>https?://[^)\s]+)(?:\s+"[^"]*")?\s*\)'
)

# 本地图片目录名（与 Markdown 文件同级）
_IMAGE_DIR_NAME = "image"

# 支持的图片扩展名
_VALID_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# Content-Type -> 扩展名兜底映射
_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}

# 下载请求头，避免部分对象存储因缺少 UA 拒绝
_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DocMindImageFetcher/1.0)"
}

# 单张图片下载超时（连接, 读取）秒
_DOWNLOAD_TIMEOUT = (10, 30)


def _safe_filename(index: int, url: str, content_type: str = "") -> str:
    """
    由图片 URL 生成稳定、合法且不易重名的本地文件名

    优先保留原始文件名主干，扩展名依次尝试：URL 后缀 -> Content-Type -> .png；
    以序号前缀保证同一 Markdown 内不重名。
    """
    name = Path(unquote(urlsplit(url).path)).name
    stem = Path(name).stem or f"image_{index}"
    # 过滤非法字符，避免路径穿越与文件名异常
    stem = re.sub(r'[\\/:*?"<>|\s]+', "_", stem).strip("_") or f"image_{index}"

    ext = Path(name).suffix.lower()
    if ext not in _VALID_IMAGE_EXT:
        ext = _CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip().lower(), ".png")

    return f"{index:03d}_{stem}{ext}"


def _validate_state_input_path(self, state: ImportGraphState) -> Tuple[Path, Path]:
    """
    验证输入路径

    Args:
        state: 该节点接收到的状态

    Returns:
        (import_file_path_obj, file_dir_path_obj) 元组
    """
    import_file_path = state.get("import_file_path", None)
    if not import_file_path:
        raise ValidationError("输入文件路径不存在", self.name)

    file_dir = state.get("file_dir", None)
    if not file_dir:
        file_dir = import_file_path

    import_file_path_obj = Path(import_file_path)
    file_dir_obj = Path(file_dir)
    if not import_file_path_obj.exists():
        raise FileProcessingError("输入文件路径不存在", self.name)
    if not file_dir_obj.exists():
        raise FileProcessingError("文件目录路径不存在", self.name)

    return import_file_path_obj, file_dir_obj


class PdfToMdNode(BaseNode):
    """
    PDF 转 Markdown 节点

    调用 DocMind 将 PDF 转换为 Markdown，
    支持实时输出转换日志。
    """

    name = "pdf_to_md_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """
        执行 PDF 转换

        Args:
            state: 图状态

        Returns:
            更新后的状态（包含 md_path）
        """

        # 1. 参数校验
        import_file_path_obj, file_dir_obj = _validate_state_input_path(self, state)

        # 2. pdf转md（调用 DocMind），返回生成的 Markdown 文件路径
        md_path = self._execute_pdf_to_md(import_file_path_obj, file_dir_obj)

        # 3. 获取md文件路径
        if not md_path.exists():
            raise FileProcessingError(f"DocMind 未生成 Markdown 文件: {md_path}", self.name)

        # 4. 修改状态
        state["md_path"] = str(md_path)
        state["file_dir"] = str(file_dir_obj)
        state["pdf_path"] = str(import_file_path_obj.parent)
        return state

    def _execute_pdf_to_md(self, import_file_path_obj: Path, file_dir_obj: Path) -> Path:
        """
        调用 DocMind 将 PDF 解析为 Markdown 并落盘

        Args:
            import_file_path_obj: 待转换的 PDF 文件全路径
            file_dir_obj: Markdown 输出目录

        Returns:
            生成的 Markdown 文件路径
        """
        cfg = self.config
        md_path = file_dir_obj / f"{import_file_path_obj.stem}.md"

        client = DocMindClient(
            enhancement_mode=cfg.docmind_enhancement_mode,
            llm_enhancement=cfg.docmind_llm_enhancement,
            poll_interval=cfg.docmind_poll_interval,
            timeout=cfg.docmind_timeout,
            layout_step_size=cfg.docmind_layout_step_size,
        )

        try:
            markdown = client.parse_to_markdown(import_file_path_obj)
        except Exception as e:
            raise FileProcessingError(f"DocMind 解析失败: {e}", self.name)

        file_dir_obj.mkdir(parents=True, exist_ok=True)

        # 将 Markdown 里的在线图片下载到本地 image 目录，并把链接改写为本地相对路径
        markdown = self._localize_images(markdown, file_dir_obj)

        md_path.write_text(markdown, encoding="utf-8")
        self.log_step("pdf_to_md", f"DocMind 已输出 Markdown: {md_path}")
        return md_path

    def _localize_images(self, markdown: str, file_dir_obj: Path) -> str:
        """
        把 Markdown 中引用的在线图片下载到本地，并将链接改写为相对路径

        单张图片下载失败时保留其原始在线链接，不中断整体流程。

        Args:
            markdown: DocMind 返回的原始 Markdown 文本
            file_dir_obj: Markdown 所在目录，图片保存到该目录下的 image 子目录

        Returns:
            改写图片链接后的 Markdown 文本
        """
        image_dir = file_dir_obj / _IMAGE_DIR_NAME
        counter = {"total": 0, "saved": 0, "failed": 0}

        def _replace(match: re.Match) -> str:
            url = match.group("url")
            alt = match.group("alt")
            counter["total"] += 1
            index = counter["total"]
            try:
                file_name = self._download_image(url, image_dir, index)
            except Exception as e:
                counter["failed"] += 1
                self.logger.warning(f"图片下载失败，保留在线链接: {url} | {e}")
                return match.group(0)

            counter["saved"] += 1
            # Markdown 与 image 目录同级，使用相对路径 image/xxx 保证可移植
            return f"![{alt}]({_IMAGE_DIR_NAME}/{file_name})"

        new_markdown = _IMAGE_PATTERN.sub(_replace, markdown)
        if counter["total"]:
            self.log_step(
                "pdf_to_md",
                f"图片本地化: 共 {counter['total']} 张, 成功 {counter['saved']} 张, "
                f"失败 {counter['failed']} 张, 目录 {image_dir}",
            )
        return new_markdown

    def _download_image(self, url: str, image_dir: Path, index: int) -> str:
        """
        下载单张在线图片到本地目录

        Args:
            url: 图片在线链接
            image_dir: 本地图片目录
            index: 图片序号，用于生成不重名的文件名

        Returns:
            保存后的本地文件名
        """
        response = requests.get(url, headers=_DOWNLOAD_HEADERS, timeout=_DOWNLOAD_TIMEOUT)
        response.raise_for_status()

        file_name = _safe_filename(index, url, response.headers.get("Content-Type", ""))
        image_dir.mkdir(parents=True, exist_ok=True)
        (image_dir / file_name).write_bytes(response.content)
        return file_name

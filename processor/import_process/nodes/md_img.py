"""
MarkDown图片处理节点

将MarkDownImageNode 中的逻辑拆分为四个职责单一的协作类，统一调度。
"""
import base64
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple, Dict, Deque

from openai import OpenAI

from core.exceptions import StateFieldError
from processor.import_process.base import BaseNode
from processor.import_process.exceptions import FileProcessingError, ImageProcessingError
from processor.import_process.state import ImportGraphState
from utils.client.ai_clients import AIClients
from utils.client.storage_clients import StorageClients


@dataclass
class ImageContext:
    """图片在 MD 中的上下文信息。"""
    heading: str  # 最近的章节标题
    pre_text: str  # 图片上方的正文内容
    post_text: str  # 图片下方的正文内容


@dataclass
class ImageInfo:
    """一张图片的完整信息。"""
    name: str  # 图片文件名，如 "abc123.jpg"
    path: str  # 图片完整路径
    context: ImageContext  # 在 MD 中的上下文


class MdFileHandler:
    """
    负责 MD 文件的读取、路径校验、图片目录构建以及处理后备份。
    """

    def __init__(self, logger, name):
        self.logger = logger
        self.name = name

    def read_md(self, state: ImportGraphState) -> tuple[str, Path, Path]:
        """
        从 state 中读取 md_path，校验并读取 MD 文件内容。

        返回 (MD 文本内容, MD 文件路径对象, 图片目录路径对象)。
        """
        # 从 state 获取 MD 文件路径，缺失则抛出状态字段异常
        md_path = state.get("md_path")
        if not md_path:
            raise StateFieldError(self.name, "md_path", str, "MD 文件路径不能为空")

        # 校验文件路径真实存在
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            raise FileProcessingError("MD 文件路径不存在", self.name)

        # 读取 MD 全文内容
        with open(md_path_obj, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 图片统一存放在 MD 同级目录下的 images 子目录
        return md_content, md_path_obj, md_path_obj.parent / "images"

    def backup(self, md_path_obj: Path, new_md_content: str) -> str:
        self.logger.info("【step_5】备份新文件")

        new_file_path = md_path_obj.with_name(
            f"{md_path_obj.stem}_new{md_path_obj.suffix}"
        )
        try:
            with open(new_file_path, "w", encoding="utf-8") as f:
                f.write(new_md_content)
            self.logger.info(f"处理后的文件已备份至: {new_file_path}")
        except IOError as e:
            self.logger.error(f"写入新文件失败 {new_file_path}: {e}")
            raise ImageProcessingError(
                f"文件写入失败: {e}", node_name="md_img_node"
            )
        return str(new_file_path)


class ImageScanner:
    """
    扫描图片目录，提取每张图片在 MD 中的上下文信息。
    """

    def __init__(self, logger, name):
        self.logger = logger
        self.name = name

    def scan_img_dir(self,
                     image_dir: Path,
                     md_content: str,
                     image_extensions: Set[str],
                     context_length: int) -> List[ImageInfo]:
        """
        遍历图片目录，过滤出合法图片并提取其上下文，返回 ImageInfo 列表。
        """
        image_list: List[ImageInfo] = []
        for img_path in image_dir.iterdir():
            # 过滤非文件条目（如子目录）
            if not img_path.is_file():
                self.logger.warning(f"图片路径 {img_path} 不是文件")
                continue
            # 过滤扩展名不在允许范围内的文件
            if img_path.suffix.lower() not in image_extensions:
                self.logger.warning(f"图片路径 {img_path} 扩展名不在允许范围内")
                continue

            # 提取图片在 MD 中的上下文，未找到引用则跳过
            context = self._find_context(md_content, img_path.name, context_length)
            if not context or context is None:
                self.logger.warning(
                    f"MD文件中未找到图片 {img_path.name} 的引用"
                )
                continue
            # 组装有效图片信息
            image_list.append(ImageInfo(
                name=img_path.name,
                path=str(img_path),
                context=context,
            ))
        self.logger.info(f"找到 {len(image_list)} 张有效图片")
        return image_list

    def _find_context(self,
                      md_content: str,
                      img_name: str,
                      max_chars: int = 200) -> ImageContext | None:
        """
        返回图片在 MD 中第一次出现位置的上下文，找不到返回 None。
        """
        # 构造匹配 MD 图片引用语法的正则：![alt](...img_name...)
        pattern = re.compile(
            r"!\[.*?\]\(.*?" + re.escape(img_name) + r".*?\)"
        )
        # 按照换行分割
        md_lines = md_content.split("\n")

        for line_index, line in enumerate(md_lines):
            # 没有找到图片, 继续下一行
            if not pattern.search(line):
                continue

            # 向上, 找到标题和图片中间的描述信息
            prev_title, prev_boundary = self._find_heading_above(md_lines, line_index)
            pre_content = md_lines[prev_boundary + 1:line_index]
            img_pre = self._extract_limited_context(pre_content, max_chars, direction="front")

            # 向下：找下一个标题，取图片到标题之间的内容作为下文
            next_boundary = self._find_heading_below(md_lines, line_index)
            post_content = md_lines[line_index + 1: next_boundary]
            img_post = self._extract_limited_context(
                post_content, max_chars, direction="end"
            )

            return ImageContext(
                heading=prev_title,
                pre_text=img_pre,
                post_text=img_post,
            )
        return None

    @staticmethod
    def _find_heading_above(
            md_lines: List[str], from_idx: int
    ) -> Tuple[str, int]:
        """从 from_idx 向上查找最近的标题。"""
        for i in range(from_idx - 1, -1, -1):
            if re.match(r"^#{1,6}\s+", md_lines[i]):
                return md_lines[i], i
        return "", -1

    @staticmethod
    def _find_heading_below(md_lines: List[str], from_idx: int) -> int:
        """从 from_idx 向下查找下一个标题。"""
        for i in range(from_idx + 1, len(md_lines)):
            if re.match(r"^#{1,6}\s+", md_lines[i]):
                return i
        return len(md_lines)

    @staticmethod
    def _extract_limited_context(
            lines: List[str], max_chars: int, direction: str
    ) -> str:
        """按段落分割，按 direction 方向贪心装填，保持段落完整性。"""
        current_paragraph: List[str] = []
        paragraphs: List[str] = []

        for line in lines:
            # line.strip(): 去除字符串首尾的空白字符(空格、制表符、换行符等)
            is_blank_line = not line.strip()
            is_other_image = re.match(
                r"^!\[.*?\]\(.*?\)$", line.strip()
            )

            if is_blank_line or is_other_image:
                if current_paragraph:
                    paragraphs.append("\n".join(current_paragraph))
                    current_paragraph = []
                continue

            current_paragraph.append(line)

        if current_paragraph:
            paragraphs.append("\n".join(current_paragraph))

        if direction == "front":
            paragraphs.reverse()  # 就近原则

        total = 0
        selected: List[str] = []
        for para in paragraphs:
            if (total + len(para) > max_chars) and selected:  # 至少有个段落
                break
            selected.append(para)
            total += len(para)

        if direction == "front":
            selected.reverse()  # 与原文顺序一致，利于VLM

        return "\n\n".join(selected)  # 折行并空一行


class VLMSummarizer:
    """通过阿里百炼视觉语言模型（DashScope 兼容模式）为每张图片生成中文标题/摘要。"""

    # 图片扩展名 -> data URL 的 MIME 类型，供多模态请求正确声明图像格式
    _MIME_MAP: Dict[str, str] = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }

    def __init__(self, logger: logging.Logger, name: str = "md_img_node"):
        self.logger = logger
        self.name = name

    def summarize_all(
            self,
            document_title: str,
            image_list: List[ImageInfo],
            vl_model: str,
            requests_per_minute: int,
    ) -> Dict[str, str]:
        self.logger.info("【step_3】提取图片摘要")

        summaries: Dict[str, str] = {}
        request_timestamps: Deque[float] = deque()

        try:
            client = AIClients.get_openai()
        except Exception as e:
            self.logger.warning(
                f"VLM 不可用，跳过图片摘要生成: {e}"
            )
            for img in image_list:
                summaries[img.name] = "图片描述"
            return summaries

        for img in image_list:
            self._enforce_rate_limit(
                request_timestamps, requests_per_minute
            )
            summaries[img.name] = self._summarize_one(
                client, vl_model, document_title, img
            )

        self.logger.info(f"生成 {len(summaries)} 张图片摘要")
        return summaries

    def _summarize_one(
            self, client: OpenAI, vl_model: str,
            document_title: str, img: ImageInfo,
    ) -> str:
        parts = [p for p in (
            img.context.heading,
            img.context.pre_text,
            img.context.post_text
        ) if p]
        final_context = "\n".join(parts) if parts else "暂无可用上下文"

        try:
            with open(img.path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return "暂无图片"

        # 依据实际扩展名声明 MIME 类型，未知时回退为 jpeg
        mime = self._MIME_MAP.get(
            Path(img.path).suffix.lower(), "image/jpeg"
        )

        try:
            resp = client.chat.completions.create(
                model=vl_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"任务：为Markdown文档中的图片生成一个简短的中文标题。\n"
                                f"背景信息：\n"
                                f"  1. 所属文档标题：\"{document_title}\"\n"
                                f"  2. 图片上下文：{final_context}\n"
                                f"请结合图片内容和上述上下文信息，"
                                f"用中文简要总结这张图片的内容，"
                                f"生成一个精准的中文标题（不要包含图片二字）。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}"
                            },
                        },
                    ],
                }],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            self.logger.warning(f"图片摘要生成失败 {img.path}: {e}")
            return "图片描述"

    def _enforce_rate_limit(
            self, timestamps: Deque[float],
            max_requests: int, window: int = 60,
    ):
        now = time.time()
        while timestamps and now - timestamps[0] >= window:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            sleep_dur = window - (now - timestamps[0])
            if sleep_dur > 0:
                self.logger.info(
                    f"达到速率限制，暂停 {sleep_dur:.2f} 秒..."
                )
                time.sleep(sleep_dur)
            now = time.time()
            while timestamps and now - timestamps[0] >= window:
                timestamps.popleft()

        timestamps.append(now)


class ImageUploader:
    """将本地图片上传至阿里云 OSS，并在 MD 内容中替换为远程 URL + 摘要。"""

    def __init__(self, logger: logging.Logger, name: str = "md_img_node"):
        self.logger = logger
        self.name = name

    def upload_and_replace(
            self, document_name: str, md_content: str,
            images_summaries: Dict[str, str],
            image_list: List[ImageInfo],
            oss_base_url: str,
    ) -> str:
        self.logger.info("【step_4】上传图片到阿里云 OSS 并更新MD")

        remote_urls = self._upload_all(
            document_name, image_list, oss_base_url
        )
        return self._replace_in_md(
            md_content, images_summaries, remote_urls
        )

    def _upload_all(
            self, document_name: str, image_list: List[ImageInfo],
            oss_base_url: str,
    ) -> Dict[str, str]:
        remote_urls: Dict[str, str] = {}

        # OSS 客户端为惰性单例，桶名已在初始化时绑定，此处仅需传入 object key
        try:
            oss_bucket = StorageClients.get_oss_client()
        except Exception as e:
            self.logger.warning(
                f"阿里云 OSS 不可用，所有图片保留本地路径: {e}"
            )
            for img in image_list:
                remote_urls[img.name] = img.path
            return remote_urls

        for img in image_list:
            object_name = f"{document_name}/{img.name}"
            try:
                oss_bucket.put_object_from_file(object_name, img.path)
                remote_url = f"{oss_base_url}/{object_name}"
                self.logger.info(f"{img.name} 上传成功")
                remote_urls[img.name] = remote_url
            except Exception as e:
                self.logger.warning(
                    f"{img.name} 上传失败，保留本地路径: {e}"
                )
                remote_urls[img.name] = img.path

        self.logger.info(
            f"成功处理 {len(remote_urls)} 张图片（上传至阿里云 OSS）"
        )
        return remote_urls

    @staticmethod
    def _replace_in_md(
            md_content: str,
            summaries: Dict[str, str],
            remote_urls: Dict[str, str],
    ) -> str:
        """替换 MD 中的图片引用为远程 URL + 摘要。"""
        pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")

        def replacer(match: re.Match) -> str:
            original_path = match.group(2).strip()
            file_name_in_md = Path(original_path).name
            for img_name, summary in summaries.items():
                if img_name == file_name_in_md:
                    return f"![{summary}]({remote_urls[img_name]})"
            return match.group(0)

        return pattern.sub(replacer, md_content)


class MdImgNode(BaseNode):
    """
    处理 MarkDown 图片的管道节点 —— 仅负责编排，不含业务细节。
    上传的MD中的图片, 进行处理:
        1. 图片上传
        2. 图片描述
        3. 图片上传进度
        4. 图片替换
        5. 文档备份
    """

    def __init__(self):
        super().__init__()
        self.file_handler = MdFileHandler(self.logger, self.name)
        self.scanner = ImageScanner(self.logger, self.name)
        self.summarizer = VLMSummarizer(self.logger, self.name)
        self.uploader = ImageUploader(self.logger, self.name)

    name = "md_img_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 1. 文件处理 -->  MD 文件的读取、路径校验、图片目录构建以及处理后备份
        md_content, md_path_obj, image_dir = self.file_handler.read_md(state)
        if not image_dir.exists():
            self.logger.warning(f"文件 {md_path_obj.name} 暂无图片要处理")
            state['md_content'] = md_content
            return state

        # 2. 获取图片上下文 --> 扫描图片目录，提取每张图片在 MD 中的上下文信息
        image_list = self.scanner.scan_img_dir(
            image_dir, md_content,
            image_extensions=self.config.image_extensions,
            context_length=self.config.img_content_length,
        )

        # 3. 通过VLM生成图片摘要 --> 通过视觉语言模型为每张图片生成中文标题/摘要
        summaries = self.summarizer.summarize_all(
            document_title=md_path_obj.stem,
            image_list=image_list,
            vl_model=self.config.vl_model,
            requests_per_minute=self.config.requests_per_minute,
        )

        # 4. 图片上传, 替换文件路径, 并插入摘要信息 --> 上传图片到阿里云 OSS
        new_md_content = self.uploader.upload_and_replace(
            document_name=md_path_obj.stem,
            md_content=md_content,
            images_summaries=summaries,
            image_list=image_list,
            oss_base_url=self.config.get_oss_base_url(),
        )

        # 5. 文档备份 --> 备份替换后的md文档
        # 5. 备份
        self.file_handler.backup(md_path_obj, new_md_content)

        # 6. 更新并返回 state
        state["md_content"] = new_md_content
        return state

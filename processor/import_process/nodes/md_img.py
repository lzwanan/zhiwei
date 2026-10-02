"""
MarkDown图片处理节点

将MarkDownImageNode 中的逻辑拆分为四个职责单一的协作类，统一调度。
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple

from core.exceptions import StateFieldError
from processor.import_process.base import BaseNode
from processor.import_process.exceptions import FileProcessingError
from processor.import_process.state import ImportGraphState


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

    def backup(self):
        """处理完成后对 MD 文件进行备份（待实现）。"""
        pass


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
    """
    通过视觉语言模型为每张图片生成中文标题/摘要。
    """

    def summarizer_all(self):
        """批量调用 VLM 为所有图片生成中文标题/摘要（待实现）。"""
        pass


class ImageUploader:
    """
    上传图片到OSS 并在 MD 内容中替换为远程 URL + 摘要
    """

    def upload_and_replace(self):
        """上传图片到 OSS，并在 MD 中将本地路径替换为远程 URL + 摘要（待实现）。"""
        pass


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
        self.md_file_handler = MdFileHandler(self.logger, self.name)
        self.image_scanner = ImageScanner(self.logger, self.name)
        self.vlm_summarizer = VLMSummarizer(self.logger, self.name)
        self.image_uploader = ImageUploader(self.logger, self.name)

    name = "md_img_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 1. 文件处理 -->  MD 文件的读取、路径校验、图片目录构建以及处理后备份
        md_content, md_path_obj, image_dir = self.md_file_handler.read_md(state)
        if not image_dir.exists():
            self.logger.warning(f"文件 {md_path_obj.name} 暂无图片要处理")
            state['md_content'] = md_content
            return state

        # 2. 获取图片上下文 --> 扫描图片目录，提取每张图片在 MD 中的上下文信息
        image_list = self.image_scanner.scan_img_dir(
            image_dir, md_content,
            image_extensions=self.config.image_extensions,
            context_length=self.config.img_content_length,
        )
        # 3. 通过VLM生成图片摘要 --> 通过视觉语言模型为每张图片生成中文标题/摘要

        # 4. 图片上传, 替换文件路径, 并插入摘要信息 --> 上传图片到OSS

        # 5. 文档备份 --> 备份替换后的md文档

        return state

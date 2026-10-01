"""
MarkDown图片处理节点

将MarkDownImageNode 中的逻辑拆分为四个职责单一的协作类，统一调度。
"""
from processor.import_process.base import BaseNode
from processor.import_process.state import ImportGraphState


class MdFileHandler:
    """
    负责 MD 文件的读取、路径校验、图片目录构建以及处理后备份。
    """

    def read_md(self):
        pass

    def backup(self):
        pass


class ImageScanner:
    """
    扫描图片目录，提取每张图片在 MD 中的上下文信息。
    """

    def scan_img_dir(self):
        pass


class VLMSummarizer:
    """
    通过视觉语言模型为每张图片生成中文标题/摘要。
    """

    def summarizer_all(self):
        pass


class ImageUploader:
    """
    上传图片到OSS 并在 MD 内容中替换为远程 URL + 摘要
    """

    def upload_and_replace(self):
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

    name = "md_img_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 1. 文件处理 -->  MD 文件的读取、路径校验、图片目录构建以及处理后备份

        # 2. 获取图片上下文 --> 扫描图片目录，提取每张图片在 MD 中的上下文信息

        # 3. 通过VLM生成图片摘要 --> 通过视觉语言模型为每张图片生成中文标题/摘要

        # 4. 图片上传, 替换文件路径, 并插入摘要信息 --> 上传图片到OSS

        # 5. 文档备份 --> 备份替换后的md文档

        return state

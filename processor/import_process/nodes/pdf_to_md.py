"""
PDF 转 Markdown 节点

使用 DocMind 将 PDF 文档转换为 Markdown 格式
"""
from pathlib import Path
from typing import Tuple

from processor.import_process.base import BaseNode
from processor.import_process.exceptions import ValidationError, FileProcessingError
from processor.import_process.state import ImportGraphState
from utils.client.docmind_client import DocMindClient


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
        md_path.write_text(markdown, encoding="utf-8")
        self.log_step("pdf_to_md", f"DocMind 已输出 Markdown: {md_path}")
        return md_path

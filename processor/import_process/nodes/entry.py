from pathlib import Path

import json

from core.paths import DOCS_DIR, TEMP_DIR
from processor.import_process.base import BaseNode, setup_logging
from processor.import_process.exceptions import ValidationError
from processor.import_process.state import ImportGraphState, create_default_state


class EntryNode(BaseNode):
    """
    Entry Node
    根据上传文件拓展名, 来决定走哪个处理分支
    """

    name = "entry_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """
        进入处理流程, 由父节点定义, 子节点进行实现
        :param state: 全局状态
        :return: 处理后的状态
        """

        # 1. 获取上传的文件
        self.log_step("step 1", "获取文件目录")
        import_file_path = state.get("import_file_path", None)

        # 2. 判断文件是否为空
        self.log_step("step 2", "判断文件是否为空")
        if not import_file_path:
            raise ValidationError(f"上传的文件不能为空", self.name)

        # 3. 获取文件拓展名
        self.log_step("step 3", "获取文件拓展名")
        path = Path(import_file_path)
        if not path.exists():
            raise ValidationError(f"上传的文件 {import_file_path} 不存在", self.name)

        self.log_step("step 4", "判断文件是否存在")
        suffix = path.suffix.lower()

        self.log_step("step 5", "判断文件类型")
        # 4. 不同文件类型, 不同状态处理
        if suffix == ".pdf":
            state['is_pdf_read_enabled'] = True
            state['pdf_path'] = import_file_path
        elif suffix == ".md":
            state['is_md_read_enabled'] = True
            state['md_path'] = import_file_path
        else:
            raise ValidationError(f"不支持的文件 {import_file_path} 类型 {suffix}", self.name)
        self.log_step("step 6", "更新文件标题")

        # 5. 文件的标题(不带拓展名的文件名)
        self.log_step("step 7", "获取文件标题")
        file_name = path.stem

        self.log_step("step 8", "更新状态")
        # 6. 更新状态
        state['file_title'] = file_name

        return state


if __name__ == "__main__":
    setup_logging()

    import_file_path = str(DOCS_DIR / "H3C-LA2608.pdf")
    file_dir = str(TEMP_DIR)
    state = {
        "is_pdf_read_enabled": False,
        "is_md_read_enabled": False,
        "file_dir": file_dir,
        "import_file_path": import_file_path
    }
    entity = EntryNode(state)

    process_state = entity.process(state)

    print(json.dumps(process_state, indent=4, ensure_ascii=False))

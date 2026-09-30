from processor.import_process.base import BaseNode
from processor.import_process.state import ImportGraphState


class MdImgNode(BaseNode):
    name = "md_img_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        pass

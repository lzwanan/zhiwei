from processor.import_process.base import BaseNode, T
from processor.import_process.state import ImportGraphState


class ItemNameRecNode(BaseNode):
    name = "item_name_rec_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        pass

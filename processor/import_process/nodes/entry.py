from processor.import_process.base import BaseNode, T
from processor.import_process.state import ImportGraphState


class EntryNode(BaseNode):
    name = "entry_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        return state

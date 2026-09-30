from processor.import_process.base import BaseNode, T
from processor.import_process.state import ImportGraphState


class BgeEmbeddingNode(BaseNode):
    name = "bge_embedding_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        return state

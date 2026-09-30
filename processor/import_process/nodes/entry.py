from processor.import_process.base import BaseNode, T
from processor.import_process.state import ImportGraphState


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
        return state

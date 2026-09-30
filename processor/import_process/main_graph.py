"""
    导入流程 [pdf or md]
        entry_node
              │
              ├── (PDF) ──> pdf_to_md_node ──┐
              │                              │
              └── (MD) ─────────────────────>├──> md_img_node
                                              │
                                              v
                                      document_split_node
                                              │
                                              v
                                      item_name_rec_node
                                              │
                                              v
                                        bge_embedding_node
                                              │
                                              v
                                        import_milvus_node
                                              │
                                              v
                                             END
"""
from langgraph.graph.state import CompiledStateGraph, StateGraph

from processor.import_process.nodes.bge_embedding import BgeEmbeddingNode
from processor.import_process.nodes.ducment_split import DocumentSplitNode
from processor.import_process.nodes.entry import EntryNode
from processor.import_process.nodes.import_milvus import ImportMilvusNode
from processor.import_process.nodes.item_name_recognition import ItemNameRecNode
from processor.import_process.nodes.md_img import MdImgNode
from processor.import_process.nodes.pdf_to_md import PdfToMdNode


def create_import_graph() -> CompiledStateGraph:
    """
        创建导入流程图

    :return: CompiledStateGraph 图对象
    """

    # 1. 创建
    graph = StateGraph()

    # 2. 设置开始节点
    graph.set_entry_point("entry_node")

    # 3. 添加节点
    nodes = {
        "entry_node": EntryNode(),
        "pdf_to_md_node": PdfToMdNode(),
        "md_img_node": MdImgNode(),
        "document_split_node": DocumentSplitNode(),
        "item_name_rec_node": ItemNameRecNode(),
        "bge_embedding_node": BgeEmbeddingNode(),
        "import_milvus_node": ImportMilvusNode(),
    }

    # 4. 添加边

    # 5. 编译成图对象

    return None

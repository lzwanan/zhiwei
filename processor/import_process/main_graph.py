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
import json

from langgraph.constants import END
from langgraph.graph.state import CompiledStateGraph, StateGraph

from processor.import_process.nodes.bge_embedding import BgeEmbeddingNode
from processor.import_process.nodes.ducment_split import DocumentSplitNode
from processor.import_process.nodes.entry import EntryNode
from processor.import_process.nodes.import_milvus import ImportMilvusNode
from processor.import_process.nodes.item_name_recognition import ItemNameRecNode
from processor.import_process.nodes.md_img import MdImgNode
from processor.import_process.nodes.pdf_to_md import PdfToMdNode
from processor.import_process.state import ImportGraphState, create_default_state


def import_router(state: ImportGraphState) -> str:
    """
        根据状态路由，返回下一个节点

    :param state: 当前状态图
    :return: 下一个节点
    """
    if state.get("is_md_read_enabled"):
        return "md"
    elif state.get("is_pdf_read_enabled"):
        return "pdf"
    else:
        return "END"


def create_import_graph() -> CompiledStateGraph:
    """
        创建导入流程图

    :return: CompiledStateGraph 图对象
    """

    # 1. 创建
    graph = StateGraph(ImportGraphState)

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

    for name, node in nodes.items():
        graph.add_node(name, node)

    # 4. 添加条件边
    graph.add_conditional_edges(
        "entry_node",
        import_router,
        {
            "pdf": "pdf_to_md_node",
            "md": "md_img_node",
            "END": END
        },
    )

    # 5. 添加顺序边
    graph.add_edge("pdf_to_md_node", "document_split_node")
    graph.add_edge("md_img_node", "document_split_node")
    graph.add_edge("document_split_node", "item_name_rec_node")
    graph.add_edge("item_name_rec_node", "bge_embedding_node")
    graph.add_edge("bge_embedding_node", "import_milvus_node")
    graph.add_edge("import_milvus_node", END)

    # 5. 编译成图对象
    return graph.compile()


import_graph = create_import_graph()


def run_import_graph(import_file_path: str, file_dir: str) -> dict:
    state = {
        "is_pdf_read_enabled": True,
        "is_md_read_enabled": False,
        "file_dir": file_dir,
        "import_file_path": import_file_path
    }
    init_state = create_default_state(**state)

    final_state = None
    for event in import_graph.stream(init_state):
        for node_name, state in event.items():
            print(f"运行节点: {node_name}")
            final_state = state

    return final_state


if __name__ == "__main__":
    import_file_path = r"../test/docs/H3C-LA2608.pdf"
    file_dir = r"../test/temp_dir"

    # 验证导入流程
    final_state = run_import_graph(import_file_path, file_dir)

    print(json.dumps(final_state, indent=2, ensure_ascii=False))

    # 打印图结构
    print("-" * 50)
    print("图结构: ")
    import_graph.get_graph().print_ascii()
    """
        运行节点: entry_node
        运行节点: pdf_to_md_node
        运行节点: document_split_node
        运行节点: item_name_rec_node
        运行节点: bge_embedding_node
        运行节点: import_milvus_node
        {
          "task_id": "",
          "is_md_read_enabled": false,
          "is_pdf_read_enabled": true,
          "import_file_path": "../test/docs/H3C-LA2608.pdf",
          "file_dir": "../test/temp_dir",
          "pdf_path": "",
          "md_path": "",
          "file_title": "",
          "item_name": "",
          "md_content": "",
          "chunks": []
        }
        --------------------------------------------------
        图结构: 
                                      +-----------+                        
                                      | __start__ |                        
                                      +-----------+                        
                                             *                             
                                             *                             
                                             *                             
                                      +------------+                       
                                      | entry_node |.                      
                                 .....+------------+ ....                  
                            .....           .            .....             
                       .....               .                  .....        
                    ...                    .                       ....    
        +-------------+           +----------------+                   ... 
        | md_img_node |           | pdf_to_md_node |                     . 
        +-------------+           +----------------+                     . 
                      **            **                                   . 
                        **        **                                     . 
                          **    **                                       . 
                  +---------------------+                                . 
                  | document_split_node |                                . 
                  +---------------------+                                . 
                             *                                           . 
                             *                                           . 
                             *                                           . 
                  +--------------------+                                 . 
                  | item_name_rec_node |                                 . 
                  +--------------------+                                 . 
                             *                                           . 
                             *                                           . 
                             *                                           . 
                  +--------------------+                                 . 
                  | bge_embedding_node |                                 . 
                  +--------------------+                                 . 
                             *                                           . 
                             *                                           . 
                             *                                           . 
                  +--------------------+                               ... 
                  | import_milvus_node |                           ....    
                  +--------------------+                      .....        
                                    ***                  .....             
                                       **            ....                  
                                         **       ...                      
                                        +---------+                        
                                        | __end__ |                        
                                        +---------+                        

    """
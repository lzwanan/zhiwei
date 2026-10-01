from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class VectorSearchNode(BaseNode):
    """向量检索节点（空壳，具体逻辑待实现）。

    职责：对原始查询做稠密向量检索。

    输入 state:
        - original_query / rewritten_query: 查询文本
        - item_names: 用于过滤的项目名称（可选）
    输出 state:
        - embedding_chunks: 稠密向量检索结果列表

    可用工具：
        - AIClients.embed([query], text_type="query")   # 生成查询向量(dense, dim=1024)
        - execute_dense_search(...)                      # utils/milvus_util.py 单路稠密检索
    """

    name = "vector_search_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现向量检索逻辑，产出 embedding_chunks
        # 注意：本节点处于并行分支，务必只返回自己产出的字段（空壳返回 {}），
        #      不要返回整个 state，否则会与并发分支重复写同一 channel 触发 InvalidUpdateError。
        return {}

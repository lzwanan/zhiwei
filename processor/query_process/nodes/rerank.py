from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class RerankNode(BaseNode):
    """重排序节点（空壳，具体逻辑待实现）。

    职责：对 RRF 融合后的候选切片，用重排序模型做相关性精排。

    输入 state:
        - original_query / rewritten_query: 查询文本
        - rrf_chunks: RRF 融合后的切片列表
    输出 state:
        - reranked_docs: 重排序后的文档列表

    可用工具：
        - AIClients.get_rerank_client().rerank(query, documents, top_n)
          # 返回 [(原始索引, 相关性分数), ...]，按分数降序
    相关配置：config.rerank_max_top_k / config.rerank_min_top_k / config.rerank_gap_abs
    """

    name = "rerank_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现重排序逻辑
        return state

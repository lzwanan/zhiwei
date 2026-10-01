from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class RrfNode(BaseNode):
    """RRF 倒数排名融合节点（空壳，具体逻辑待实现）。

    职责：融合多路检索结果（向量 + HyDE + 网页搜索），按 RRF 算法重排。

    输入 state:
        - embedding_chunks: 向量检索结果
        - hyde_embedding_chunks: HyDE 检索结果
        - web_search_docs: 网页搜索结果
    输出 state:
        - rrf_chunks: RRF 融合后的切片列表

    相关配置：config.rrf_k / config.rrf_max_results
    """

    name = "rrf_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现 RRF 融合逻辑
        return state

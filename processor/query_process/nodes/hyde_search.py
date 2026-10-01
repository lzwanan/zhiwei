from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class HyDeSearchNode(BaseNode):
    """HyDE 检索节点（空壳，具体逻辑待实现）。

    职责：先用 LLM 生成假设性文档，再对该文档做稠密向量检索。

    输入 state:
        - original_query / rewritten_query: 查询文本
    输出 state:
        - hyde_embedding_chunks: 基于假设性文档的检索结果列表

    可用工具：
        - AIClients.get_llm_openai("LLM_DEFAULT_MODEL")  # 生成假设性文档
        - AIClients.embed([hyde_doc], text_type="document")  # 编码假设性文档
        - execute_dense_search(...)                      # utils/milvus_util.py 单路稠密检索
    """

    name = "hyde_search_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现 HyDE 检索逻辑，产出 hyde_embedding_chunks
        # 注意：本节点处于并行分支，务必只返回自己产出的字段（空壳返回 {}），
        #      不要返回整个 state，否则会与并发分支重复写同一 channel 触发 InvalidUpdateError。
        return {}

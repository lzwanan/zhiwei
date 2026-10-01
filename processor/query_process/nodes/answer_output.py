from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class AnswerOutputNode(BaseNode):
    """答案输出节点（空壳，具体逻辑待实现）。

    职责：基于精排后的文档构建提示词，调用 LLM 生成最终答案（支持流式）。

    输入 state:
        - original_query / rewritten_query: 查询文本
        - reranked_docs: 重排序后的文档
        - item_names: 项目名称
        - history / is_stream / task_id / session_id / message_id
    输出 state:
        - prompt: 拼装后的提示词
        - answer: 最终答案

    可用工具：
        - AIClients.get_llm_openai("LLM_DEFAULT_MODEL", response_format=False)
        - prompt/query_prompt.py  # 提示词模板
    相关配置：config.max_context_chars
    """

    name = "answer_output_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现答案生成逻辑
        return state

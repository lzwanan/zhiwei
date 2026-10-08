from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class SubjectConfirmNode(BaseNode):
    """主题实体确认节点（空壳，具体逻辑待实现）。

    职责：识别/确认用户问题指向的主题实体（产品/项目/制度/系统/流程等），
    决定是否需要澄清或直接回答。

    输入 state:
        - original_query: 原始查询
        - history: 历史对话
        - session_id / message_id
    输出 state:
        - subjects: 确认后的主题实体列表
        - rewritten_query: 重写后的查询（可选）
        - answer: 若可直接回答则填充，触发跳过搜索的路由

    可用工具：
        - AIClients.get_subject_llm()         # SUBJECT_MODEL，输出 JSON
        - AIClients.embed([...], "query")     # 主题实体向量匹配
    相关配置：config.subject_high_confidence / subject_mid_confidence / subject_max_options
    """

    name = "subject_confirm_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现主题实体确认逻辑
        return state

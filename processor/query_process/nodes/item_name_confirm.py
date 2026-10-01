from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class ItemNameConfirmNode(BaseNode):
    """项目名称确认节点（空壳，具体逻辑待实现）。

    职责：识别/确认用户问题指向的项目名称，决定是否需要澄清或直接回答。

    输入 state:
        - original_query: 原始查询
        - history: 历史对话
        - session_id / message_id
    输出 state:
        - item_names: 确认后的项目名称列表
        - rewritten_query: 重写后的查询（可选）
        - answer: 若可直接回答则填充，触发跳过搜索的路由

    可用工具：
        - AIClients.get_item_llm()          # ITEM_MODEL，输出 JSON
        - AIClients.embed([...], "query")   # 项目名向量匹配
    相关配置：config.item_name_high_confidence / item_name_mid_confidence / item_name_max_options
    """

    name = "item_name_confirm_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现项目名确认逻辑
        return state

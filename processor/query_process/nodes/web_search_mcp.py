from processor.query_process.base import BaseNode
from processor.query_process.state import QueryGraphState


class WebSearchMcpNode(BaseNode):
    """网络搜索节点（空壳，具体逻辑待实现）。

    职责：通过 DashScope MCP WebSearch 工具获取联网搜索结果。

    输入 state:
        - original_query / rewritten_query: 查询文本
    输出 state:
        - web_search_docs: 网页搜索结果列表

    可用工具：
        - config.mcp_dashscope_base_url     # MCP WebSearch 服务地址
    """

    name = "web_search_mcp_node"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # TODO: 实现网络搜索逻辑，产出 web_search_docs
        # 注意：本节点处于并行分支，务必只返回自己产出的字段（空壳返回 {}），
        #      不要返回整个 state，否则会与并发分支重复写同一 channel 触发 InvalidUpdateError。
        return {}

"""
向量嵌入工具（阿里云百炼 text-embedding，纯稠密向量）

迁移说明：
- 旧实现基于本地 BGE-M3，输出 dense + sparse 混合向量；
- 新实现对接百炼 text-embedding-v4，仅输出稠密(dense)向量，不再产生稀疏向量。
"""
from typing import List, Optional

from openai import OpenAI


def generate_dense_embeddings(
    client: OpenAI,
    model: str,
    texts: List[str],
    text_type: str = "document",
    dimensions: Optional[int] = None,
) -> List[List[float]]:
    """
    调用阿里云百炼 text-embedding 生成稠密向量。

    Args:
        client: OpenAI 兼容客户端（AIClients.get_embedding_client()）
        model: embedding 模型名，例如 text-embedding-v4
        texts: 待编码文本列表
        text_type: "query"（检索查询）或 "document"（入库文档），
                   百炼通过该参数区分非对称检索前缀
        dimensions: 输出向量维度，None 使用模型默认维度

    Returns:
        二维稠密向量列表：[[float, ...], ...]，顺序与 texts 对应

    Raises:
        ValueError: 输入参数无效
        RuntimeError: 嵌入生成失败
    """
    # 1. 参数校验
    if not texts:
        raise ValueError("texts 不能为空")

    if not all(isinstance(t, str) and t.strip() for t in texts):
        raise ValueError("texts 中存在无效元素（空字符串或非字符串类型）")

    if text_type not in ("query", "document"):
        raise ValueError(f"text_type 非法:{text_type}，仅支持 'query' 或 'document'")

    # 2. 生成嵌入（百炼通过 extra_body 传递 text_type / dimensions 等非标准参数）
    extra_body = {"text_type": text_type}
    if dimensions is not None:
        extra_body["dimensions"] = dimensions

    try:
        resp = client.embeddings.create(
            model=model,
            input=texts,
            extra_body=extra_body,
        )
    except Exception as e:
        raise RuntimeError(f"百炼 Embedding 生成失败: {e}") from e

    # 3. 校验嵌入结果
    if not resp.data:
        raise RuntimeError("百炼 Embedding 返回结果为空")

    # 4. 解析稠密向量
    embeddings = [item.embedding for item in resp.data]

    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"嵌入结果数量({len(embeddings)})与输入文本数量({len(texts)})不一致"
        )

    return embeddings

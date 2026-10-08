"""查询流程自定义异常类

统一错误处理，提供更清晰的错误信息。
通用异常基础设施复用 core.exceptions，避免与导入流程重复定义。
"""

from core.exceptions import (
    ProcessError,
    StateFieldError,
    ConfigurationError,
    EmbeddingError,
    LLMError,
    StorageError,
    MilvusError,
    ValidationError,
)


class QueryProcessError(ProcessError):
    """查询流程基础异常。"""
    pass


class SearchError(QueryProcessError):
    """搜索错误。

    向量搜索、混合搜索或网络搜索失败时抛出。
    """
    pass


class MongoDBError(StorageError):
    """MongoDB 存储错误。

    MongoDB 数据库操作失败时抛出。
    """
    pass


class EntityAlignmentError(QueryProcessError):
    """实体对齐错误。

    知识图谱实体对齐过程失败时抛出。
    """
    pass


class RerankError(QueryProcessError):
    """重排序错误。

    文档重排序过程失败时抛出。
    """
    pass


class SubjectConfirmError(QueryProcessError):
    """主题实体确认错误。

    主题实体识别或确认过程失败时抛出。
    """
    pass


__all__ = [
    "ProcessError",
    "QueryProcessError",
    "StateFieldError",
    "ConfigurationError",
    "SearchError",
    "EmbeddingError",
    "LLMError",
    "StorageError",
    "MilvusError",
    "MongoDBError",
    "ValidationError",
    "EntityAlignmentError",
    "RerankError",
    "SubjectConfirmError",
]

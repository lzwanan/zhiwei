"""流程共享自定义异常类

导入流程和查询流程通用的异常基础设施，避免重复定义。
"""


class ProcessError(Exception):
    """流程基础异常（导入/查询流程共享）。

    Attributes:
        node_name: 发生异常的节点名称。
        cause: 原始异常对象。
    """

    def __init__(
            self,
            message: str,
            node_name: str = "",
            cause: Exception = None
    ):
        """初始化异常。

        Args:
            message: 错误信息。
            node_name: 节点名称。
            cause: 原始异常。
        """
        self.node_name = node_name
        self.cause = cause
        super().__init__(message)

    def __str__(self):
        """格式化异常信息。

        Returns:
            包含节点名称和原因的完整错误信息。
        """
        parts = []
        if self.node_name:
            parts.append(f"[{self.node_name}]")
        parts.append(super().__str__())
        if self.cause:
            parts.append(f"(原因: {self.cause})")
        return " ".join(parts)


class StateFieldError(ProcessError):
    """状态字段错误。

    从 state 中获取必需字段缺失、为空或类型不符时抛出。

    Attributes:
        field_name: 缺失或无效的字段名称。
        expected_type: 期望的字段类型（可选）。
    """

    def __init__(
            self,
            node_name: str = "",
            field_name: str = "",
            expected_type: type = None,
            message: str = "",
            cause: Exception = None,
    ):
        self.field_name = field_name
        self.expected_type = expected_type
        if not message:
            message = f"状态字段 '{field_name}' 缺失或无效"
            if expected_type:
                message += f"，期望类型: {expected_type.__name__}"
        super().__init__(message, node_name=node_name, cause=cause)


class ConfigurationError(ProcessError):
    """配置错误。

    环境变量缺失或配置值无效时抛出。
    """
    pass


class EmbeddingError(ProcessError):
    """向量化错误。

    模型调用失败、向量生成异常时抛出。
    """
    pass


class LLMError(ProcessError):
    """LLM 调用错误。

    API 调用失败、响应解析失败时抛出。
    """
    pass


class StorageError(ProcessError):
    """存储错误。

    数据库操作失败时抛出。
    """
    pass


class MilvusError(StorageError):
    """Milvus 存储错误。

    Milvus 向量数据库操作失败时抛出。
    """
    pass


class ValidationError(ProcessError):
    """数据验证错误。

    输入数据不符合预期时抛出。
    """
    pass

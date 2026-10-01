"""
导入流程自定义异常类

统一错误处理，提供更清晰的错误信息。
通用异常基础设施复用 core.exceptions，避免与查询流程重复定义。
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


class ImportProcessError(ProcessError):
    """导入流程基础异常"""
    pass


class FileProcessingError(ImportProcessError):
    """文件处理错误：文件不存在、格式错误、读写失败"""
    pass


class PdfConversionError(FileProcessingError):
    """PDF 转换错误：转换失败"""
    pass


class ImageProcessingError(FileProcessingError):
    """图片处理错误：图片总结、上传失败"""
    pass


class DocumentSplitError(ImportProcessError):
    """文档切分错误：切分逻辑异常"""
    pass


class MinioError(StorageError):
    """MinIO 存储错误"""
    pass


__all__ = [
    "ProcessError",
    "ImportProcessError",
    "StateFieldError",
    "ConfigurationError",
    "FileProcessingError",
    "PdfConversionError",
    "ImageProcessingError",
    "DocumentSplitError",
    "EmbeddingError",
    "LLMError",
    "StorageError",
    "MilvusError",
    "MinioError",
    "ValidationError",
]

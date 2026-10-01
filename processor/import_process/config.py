"""
导入流程配置管理模块

集中管理所有配置项，支持环境变量覆盖
"""
import threading
from dataclasses import dataclass, field
from typing import Set, Optional
import os
from dotenv import load_dotenv

load_dotenv()

"""
@dataclass:是 Python 3.7+ 引入的装饰器，用于自动生成类的样板代码。
它会自动为类生成以下方法：
__init__() - 构造函数
__repr__() - 字符串表示
__eq__() - 相等比较
__hash__() - 哈希（可选）
"""

@dataclass
class ImportConfig:
    """导入流程配置"""

    # ==================== 文档处理配置 ====================
    max_content_length: int = 1000  # 切片最大长度
    img_content_length: int = 200  # 图片上下文最大长度
    min_content_length: int = 500  # 合并短内容的最小长度
    overlap_sentences: int = 1  # 句子级切分时的重叠句数
    item_name_chunk_k: int = 3  # 项目名识别时使用的切片数量
    item_name_chunk_size: int = 2500  # 项目名识别时使用的切片内容长度


    """
    对于你的场景（从环境变量读取配置），必须使用 field(default_factory=lambda: ...)，因为：
    ✅ 支持运行时环境变量变化 ✅ 避免模块加载时序问题 ✅ 保持代码风格一致 ✅ 更符合配置管理的最佳实践
    如果直接赋值，可能会导致环境变量修改后不生效的 bug！
    """
    image_extensions: Set[str] = field(
        default_factory=lambda: {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    )

    # ==================== LLM 配置 ====================
    openai_api_base: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_BASE", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    vl_model: str = field(
        default_factory=lambda: os.getenv("VL_MODEL", "")
    )
    item_model: str = field(
        default_factory=lambda: os.getenv("ITEM_MODEL", "")
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("MODEL", "")
    )

    # ==================== Milvus 配置 ====================
    milvus_url: str = field(
        default_factory=lambda: os.getenv("MILVUS_URL", "")
    )
    chunks_collection: str = field(
        default_factory=lambda: os.getenv("CHUNKS_COLLECTION", "")
    )
    item_name_collection: str = field(
        default_factory=lambda: os.getenv("ITEM_NAME_COLLECTION", "")
    )
    entity_name_collection: str = field(
        default_factory=lambda: os.getenv("ENTITY_NAME_COLLECTION", "")
    )

    # ==================== MinIO 配置 ====================
    minio_endpoint: str = field(
        default_factory=lambda: os.getenv("MINIO_ENDPOINT", "")
    )
    minio_access_key: str = field(
        default_factory=lambda: os.getenv("MINIO_ACCESS_KEY", "")
    )
    minio_secret_key: str = field(
        default_factory=lambda: os.getenv("MINIO_SECRET_KEY", "")
    )
    minio_bucket: str = field(
        default_factory=lambda: os.getenv("MINIO_BUCKET_NAME", "")
    )
    minio_secure: bool = False

    # ==================== 向量配置 ====================
    embedding_dim: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024"))
    )
    embedding_batch_size: int = 8

    # ==================== 速率限制 ====================
    requests_per_minute: int = 10  # 图片总结 API 速率限制

    # ==================== DocMind 配置（PDF 转 Markdown，阿里云 POP 通道） ====================
    docmind_access_key_id: str = field(
        default_factory=lambda: os.getenv("DOCMIND_ACCESS_KEY_ID", "")
    )
    docmind_access_key_secret: str = field(
        default_factory=lambda: os.getenv("DOCMIND_ACCESS_KEY_SECRET", "")
    )
    docmind_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "DOCMIND_ENDPOINT", "docmind-api.cn-hangzhou.aliyuncs.com"
        )
    )
    # 增强模式：留空/AUTO/BASE=基础链路；VLM=多模态大模型增强（需配合 docmind_llm_enhancement）
    docmind_enhancement_mode: str = field(
        default_factory=lambda: os.getenv("DOCMIND_ENHANCEMENT_MODE", "AUTO")
    )
    # 是否开启 LLM 增强（语义理解/内容增强）
    docmind_llm_enhancement: bool = field(
        default_factory=lambda: os.getenv("DOCMIND_LLM_ENHANCEMENT", "false").lower() in ("true", "1")
    )
    # 状态轮询间隔（秒）
    docmind_poll_interval: int = field(
        default_factory=lambda: int(os.getenv("DOCMIND_POLL_INTERVAL", "5"))
    )
    # 单个文档解析超时（秒）
    docmind_timeout: int = field(
        default_factory=lambda: int(os.getenv("DOCMIND_TIMEOUT", "600"))
    )
    # 结果分页拉取步长
    docmind_layout_step_size: int = field(
        default_factory=lambda: int(os.getenv("DOCMIND_LAYOUT_STEP_SIZE", "200"))
    )

    #创建实例对象
    @classmethod
    def from_env(cls) -> "ImportConfig":
        """从环境变量加载配置"""
        return cls()



    # http://192.168.6.150:9000/
    def get_minio_base_url(self):
        base_protocol = "https://" if self.minio_secure else "http://"
        return base_protocol + f"{self.minio_endpoint}"


# ==================== 全局单例 ====================
# 下划线前缀：Python 约定表示"私有"或"内部使用"
# 暗示不应该直接从模块外部访问，应该通过 get_config() 函数获取
# 注意线程安全：多线程环境需要加锁
_config: Optional[ImportConfig] = None

#_lock = threading.Lock()

# 单例获取函数
def get_config() -> ImportConfig:
    """获取配置单例"""
    global _config
    #with _lock:  # 加锁保护
    if _config is None:
        _config = ImportConfig.from_env()
    return _config

import os
import threading
from typing import Dict, List, Optional, Tuple

import httpx
from langchain_openai import ChatOpenAI
from openai import OpenAI

from utils.client.base import BaseClientManager, logger


class RerankClient:
    """阿里云百炼 GTE 重排序客户端（通过 DashScope REST 接口调用，非本地模型）。"""

    def __init__(self, api_key: str, model: str, url: str):
        self._api_key = api_key
        self._model = model
        self._url = url
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> List[Tuple[int, float]]:
        """
        对文档按与 query 的相关性重排序。

        :param query: 查询文本
        :param documents: 待排序文档列表
        :param top_n: 返回条数，默认全部
        :return: [(原始索引, 相关性分数), ...]，按分数降序
        """
        if not documents:
            return []

        payload = {
            "model": self._model,
            "input": {"query": query, "documents": documents},
            "parameters": {
                "return_documents": False,
                "top_n": top_n or len(documents),
            },
        }
        try:
            resp = httpx.post(self._url, headers=self._headers, json=payload, timeout=30)
            resp.raise_for_status()
            results = resp.json()["output"]["results"]
        except Exception as e:
            logger.error(f"百炼 Rerank 调用失败: {e}")
            raise ConnectionError(f"百炼 Rerank 调用失败: {e}") from e

        return [(r["index"], r["relevance_score"]) for r in results]


class AIClients(BaseClientManager):
    """
    AI 模型客户端：全部对接阿里云百炼（DashScope），不使用任何本地模型。
      - OpenAI 兼容客户端：Chat + Embedding 复用
      - ChatOpenAI：按 (模型环境变量, response_format) 缓存多个 LLM
      - RerankClient：百炼 gte-rerank
    """

    # ==================== OpenAI 兼容原生客户端（Chat + Embedding 复用） ====================
    _openai_client: Optional[OpenAI] = None
    _openai_lock = threading.Lock()

    @classmethod
    def get_openai(cls) -> OpenAI:
        return cls._get_or_create("_openai_client", cls._openai_lock, cls._create_openai)

    @classmethod
    def _create_openai(cls) -> OpenAI:
        try:
            api_key = cls._require_env("DASHSCOPE_API_KEY")
            base_url = cls._require_env("OPENAI_API_BASE")
            client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info(f"OpenAI(百炼兼容) 客户端创建成功:{base_url}")
            return client
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"OpenAI(百炼兼容) 客户端创建失败:{e}")
            raise ConnectionError(f"OpenAI(百炼兼容) 连接失败:{e}") from e

    # ==================== Embedding 客户端（百炼 text-embedding，复用 OpenAI 兼容客户端） ====================
    _embedding_model: Optional[str] = None
    _embedding_dim: Optional[int] = None

    @classmethod
    def get_embedding_client(cls) -> OpenAI:
        """返回用于 embeddings 调用的 OpenAI 兼容客户端（与 get_openai 同一单例）。"""
        return cls.get_openai()

    @classmethod
    def get_embedding_model(cls) -> str:
        """读取并缓存百炼 embedding 模型名（EMBEDDING_MODEL）。"""
        if cls._embedding_model is None:
            cls._embedding_model = cls._require_env("EMBEDDING_MODEL")
        return cls._embedding_model

    @classmethod
    def get_embedding_dim(cls) -> Optional[int]:
        """读取并缓存输出向量维度（EMBEDDING_DIM），未配置时返回 None（使用模型默认维度）。"""
        if cls._embedding_dim is None:
            dim = os.getenv("EMBEDDING_DIM")
            cls._embedding_dim = int(dim) if dim else None
        return cls._embedding_dim

    @classmethod
    def embed(cls, texts: List[str], text_type: str = "document") -> List[List[float]]:
        """
        统一 embedding 入口：封装客户端、模型名与维度，供各节点直接调用。

        :param texts: 待编码文本列表
        :param text_type: "query"（检索查询）或 "document"（入库文档）
        :return: 二维稠密向量列表
        """
        from utils.embedding_util import generate_dense_embeddings

        return generate_dense_embeddings(
            client=cls.get_embedding_client(),
            model=cls.get_embedding_model(),
            texts=texts,
            text_type=text_type,
            dimensions=cls.get_embedding_dim(),
        )

    # ==================== LLM（ChatOpenAI）：按 (模型环境变量, response_format) 缓存 ====================
    _llm_clients: Dict[Tuple[str, bool], ChatOpenAI] = {}
    _llm_lock = threading.Lock()

    @classmethod
    def get_llm_openai(cls, model_env: str = "LLM_DEFAULT_MODEL", response_format: bool = False) -> ChatOpenAI:
        key = (model_env, response_format)
        client = cls._llm_clients.get(key)
        if client is not None:
            return client
        with cls._llm_lock:
            client = cls._llm_clients.get(key)
            if client is None:
                client = cls._create_llm_openai(model_env, response_format)
                cls._llm_clients[key] = client
            return client

    @classmethod
    def _create_llm_openai(cls, model_env: str, response_format: bool) -> ChatOpenAI:
        try:
            api_key = cls._require_env("DASHSCOPE_API_KEY")
            base_url = cls._require_env("OPENAI_API_BASE")
            model_name = cls._require_env(model_env)
            temperature = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.1"))

            model_kwargs = {}
            if response_format:
                model_kwargs["response_format"] = {"type": "json_object"}

            client = ChatOpenAI(
                model_name=model_name,
                openai_api_key=api_key,
                openai_api_base=base_url,
                temperature=temperature,
                model_kwargs=model_kwargs,
            )
            logger.info(f"ChatOpenAI LLM 客户端初始化成功: model={model_name}, json={response_format}")
            return client
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"ChatOpenAI LLM 客户端初始化失败:{e}")
            raise ConnectionError(f"ChatOpenAI LLM 连接失败:{e}") from e

    # ==================== 各专用模型便捷入口 ====================
    @classmethod
    def get_vl_llm(cls) -> ChatOpenAI:
        """多模态视觉模型（VL_MODEL），用于图片/多模态理解。"""
        return cls.get_llm_openai("VL_MODEL", response_format=False)

    @classmethod
    def get_item_llm(cls) -> ChatOpenAI:
        """项目名识别模型（ITEM_MODEL），输出 JSON。"""
        return cls.get_llm_openai("ITEM_MODEL", response_format=True)

    @classmethod
    def get_kg_llm(cls) -> ChatOpenAI:
        """知识图谱抽取模型（KG_MODEL），输出 JSON。"""
        return cls.get_llm_openai("KG_MODEL", response_format=True)

    # ==================== Rerank（百炼 gte-rerank） ====================
    _rerank_client: Optional[RerankClient] = None
    _rerank_lock = threading.Lock()

    @classmethod
    def get_rerank_client(cls) -> RerankClient:
        return cls._get_or_create("_rerank_client", cls._rerank_lock, cls._create_rerank_client)

    @classmethod
    def _create_rerank_client(cls) -> RerankClient:
        try:
            api_key = cls._require_env("DASHSCOPE_API_KEY")
            model = cls._require_env("RERANK_MODEL")
            url = os.getenv(
                "RERANK_API_URL",
                "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
            )
            client = RerankClient(api_key=api_key, model=model, url=url)
            logger.info(f"百炼 Rerank 客户端初始化成功: model={model}")
            return client
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"百炼 Rerank 客户端初始化失败:{e}")
            raise ConnectionError(f"百炼 Rerank 客户端创建失败:{e}") from e


if __name__ == "__main__":
    print(AIClients.get_rerank_client())

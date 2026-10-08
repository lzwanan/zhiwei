import json
import os
from json import JSONDecodeError
from typing import Dict, List, Tuple

from langchain_core.messages import SystemMessage, HumanMessage
from pymilvus import DataType

from processor.import_process.state import ImportGraphState
from processor.import_process.base import BaseNode
from processor.import_process.exceptions import (
    StateFieldError,
    ValidationError,
    EmbeddingError,
    MilvusError,
)
from utils.client.ai_clients import AIClients
from prompt.import_prompt import ITEM_NAME_SYSTEM_PROMPT, ITEM_NAME_USER_PROMPT_TEMPLATE
from utils.client.storage_clients import StorageClients


class ItemNameRecognitionNode(BaseNode):
    """商品名识别节点。

    流程：校验状态 -> 构建识别上下文 -> LLM 提取商品名（JSON）-> 生成稠密向量
    -> 写入 item_name 集合 -> 回填 state。

    说明：项目已统一对接阿里云百炼，Embedding 仅产出稠密(dense)向量，
    不再使用本地 BGE-M3 的 dense+sparse 混合向量。
    """

    name = "item_name_recognition_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 1. 参数校验
        file_title, chunks, item_name_chunks_k, item_name_chunk_size = self._validate_state(state)

        # 2. 构建商品名识别上下文
        item_name_recognition_context = self._prepare_item_name_recognition_context(
            chunks, item_name_chunks_k, item_name_chunk_size
        )

        # 3. LLM 商品名识别
        item_name = self._recognition_name(file_title, item_name_recognition_context)

        # 4. 向量化提取到的商品名（百炼稠密向量）
        dense_vector = self._embedding_item_name(item_name)

        # 5. 存储到 Milvus
        self._insert_milvus(file_title, item_name, dense_vector, self.config.item_name_collection)

        # 6. 回填 item_name 信息
        self._fill_item_name(item_name, state, chunks)

        return state

    def _validate_state(self, state: ImportGraphState) -> Tuple[str, List, int, int]:
        file_title = state.get('file_title')
        chunks = state.get('chunks')

        if not file_title:
            raise StateFieldError(node_name=self.name, field_name="file_title", expected_type=str)
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name="chunks", expected_type=list)

        item_name_chunks_k = self.config.item_name_chunk_k
        if not item_name_chunks_k or item_name_chunks_k <= 0:
            raise ValidationError(message="item_name_chunk_k为空或者无效", node_name=self.name)

        item_name_chunk_size = self.config.item_name_chunk_size
        if not item_name_chunk_size or item_name_chunk_size <= 0:
            raise ValidationError(message="item_name_chunk_size为空或者无效", node_name=self.name)

        return file_title, chunks, item_name_chunks_k, item_name_chunk_size

    def _prepare_item_name_recognition_context(self, chunks, item_name_chunks_k, item_name_chunk_size) -> str:
        total = 0
        final_context = []
        for index, chunk in enumerate(chunks[:item_name_chunks_k]):
            if not isinstance(chunk, dict):
                continue
            chunk_content = chunk.get('content')
            context = f"【切片】-{index}-{chunk_content}"

            if total + len(context) > item_name_chunk_size:
                # 兜底：首个切片即超长时截断保留，避免给 LLM 传入空上下文
                if not final_context:
                    final_context.append(context[:item_name_chunk_size])
                break

            total += len(context)
            final_context.append(context)

        return "\n".join(final_context)

    def _recognition_name(self, file_title, item_name_recognition_context) -> str:
        try:
            llm_client = AIClients.get_item_llm()
            user_prompt = ITEM_NAME_USER_PROMPT_TEMPLATE.format(
                file_title=file_title, context=item_name_recognition_context
            )

            llm_response = llm_client.invoke([
                SystemMessage(content=ITEM_NAME_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ])

            item_name = self._parse_item_name(llm_response.content)
            if not item_name or item_name.upper() == "UNKNOWN":
                self.logger.info(f"LLM未识别出商品名，降级使用标题: {file_title}")
                return file_title

            self.logger.info(f"LLM提取到商品名: {item_name}")
            return item_name
        except Exception as e:
            self.logger.error(f"LLM调用失败，降级使用标题: {file_title}，异常: {e}")
            return file_title

    @staticmethod
    def _parse_item_name(raw: str) -> str:
        """解析 LLM 输出：优先按 JSON {"item_name": ...}，兼容纯文本返回。"""
        raw = (raw or "").strip()
        if not raw:
            return ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return str(data.get("item_name", "")).strip()
        except (JSONDecodeError, TypeError):
            # 非 JSON 输出，回退按纯文本处理
            pass
        return raw

    def _embedding_item_name(self, item_name) -> List[float]:
        try:
            dense_vectors = AIClients.embed([item_name], text_type="document")
        except Exception as e:
            raise EmbeddingError(
                message=f"商品名 [{item_name}] 向量化失败", node_name=self.name, cause=e
            ) from e

        if not dense_vectors or not dense_vectors[0]:
            raise EmbeddingError(message=f"商品名 [{item_name}] 向量化结果为空", node_name=self.name)

        return dense_vectors[0]

    def _insert_milvus(self, file_title, item_name, dense_vector: List[float], item_name_collection):
        try:
            milvus_client = StorageClients.get_milvus_client()

            if not milvus_client.has_collection(item_name_collection):
                self._create_item_name_collection(item_name_collection, milvus_client)

            data = {
                "file_title": file_title,
                "item_name": item_name,
                "dense_vector": dense_vector,
            }
            result = milvus_client.insert(collection_name=item_name_collection, data=[data])
            self.logger.info(f"已成功保存到 Milvus，ID: {result['ids'][0]}")
        except Exception as e:
            raise MilvusError(
                message=f"商品名 [{item_name}] 写入 Milvus 集合 [{item_name_collection}] 失败",
                node_name=self.name, cause=e
            ) from e

    def _create_item_name_collection(self, collection_name, milvus_client):
        metric_type = os.getenv("MILVUS_METRIC_TYPE", "COSINE")

        schema = milvus_client.create_schema()
        schema.add_field(field_name="pk", datatype=DataType.VARCHAR,
                         is_primary=True, auto_id=True, max_length=100)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR,
                         dim=self.config.embedding_dim)

        index_param = milvus_client.prepare_index_params()
        index_param.add_index(field_name="dense_vector", index_name="dense_vector_index",
                              index_type="AUTOINDEX", metric_type=metric_type)

        milvus_client.create_collection(collection_name=collection_name,
                                        schema=schema, index_params=index_param)
        self.logger.info(f"集合 {collection_name} 创建成功并构建了索引")

    def _fill_item_name(self, item_name, state, chunks):
        for chunk in chunks:
            chunk['item_name'] = item_name

        state['item_name'] = item_name

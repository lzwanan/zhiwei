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
from prompt.import_prompt import DOC_META_SYSTEM_PROMPT, DOC_META_USER_PROMPT_TEMPLATE
from utils.client.storage_clients import StorageClients


class SubjectRecognitionNode(BaseNode):
    """文档元数据识别节点（通用）。

    流程：校验状态 -> 构建识别上下文 -> LLM 抽取元数据(subject/doc_type/domain)
    -> 对主题实体生成稠密向量 -> 写入 subject 集合 -> 回填 state。

    说明：面向企业级知识库，不再限定"商品/设备"，而是抽取任意文档的
    主题实体(subject)、文档类型(doc_type)、业务领域(domain)三项元数据。
    Embedding 统一走阿里云百炼，仅产出稠密(dense)向量。
    """

    name = "subject_recognition_node"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        # 1. 参数校验
        file_title, chunks, subject_chunk_k, subject_chunk_size = self._validate_state(state)

        # 2. 构建元数据识别上下文
        recognition_context = self._prepare_recognition_context(
            chunks, subject_chunk_k, subject_chunk_size
        )

        # 3. LLM 抽取文档元数据
        meta = self._recognition_meta(file_title, recognition_context)
        subject, doc_type, domain = meta["subject"], meta["doc_type"], meta["domain"]

        # 4. 向量化主题实体（百炼稠密向量）
        dense_vector = self._embedding_subject(subject)

        # 5. 存储到 Milvus
        self._insert_milvus(file_title, subject, doc_type, domain, dense_vector,
                            self.config.subject_collection)

        # 6. 回填元数据信息
        self._fill_meta(subject, doc_type, domain, state, chunks)

        return state

    def _validate_state(self, state: ImportGraphState) -> Tuple[str, List, int, int]:
        file_title = state.get('file_title')
        chunks = state.get('chunks')

        if not file_title:
            raise StateFieldError(node_name=self.name, field_name="file_title", expected_type=str)
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name="chunks", expected_type=list)

        subject_chunk_k = self.config.subject_chunk_k
        if not subject_chunk_k or subject_chunk_k <= 0:
            raise ValidationError(message="subject_chunk_k为空或者无效", node_name=self.name)

        subject_chunk_size = self.config.subject_chunk_size
        if not subject_chunk_size or subject_chunk_size <= 0:
            raise ValidationError(message="subject_chunk_size为空或者无效", node_name=self.name)

        return file_title, chunks, subject_chunk_k, subject_chunk_size

    def _prepare_recognition_context(self, chunks, subject_chunk_k, subject_chunk_size) -> str:
        total = 0
        final_context = []
        for index, chunk in enumerate(chunks[:subject_chunk_k]):
            if not isinstance(chunk, dict):
                continue
            chunk_content = chunk.get('content')
            context = f"【切片】-{index}-{chunk_content}"

            if total + len(context) > subject_chunk_size:
                # 兜底：首个切片即超长时截断保留，避免给 LLM 传入空上下文
                if not final_context:
                    final_context.append(context[:subject_chunk_size])
                break

            total += len(context)
            final_context.append(context)

        return "\n".join(final_context)

    def _recognition_meta(self, file_title, recognition_context) -> Dict[str, str]:
        # 默认降级：主题用文件名兜底，类型/领域置为通用默认值
        fallback = {"subject": file_title, "doc_type": "其他", "domain": "通用"}
        try:
            llm_client = AIClients.get_subject_llm()
            user_prompt = DOC_META_USER_PROMPT_TEMPLATE.format(
                file_title=file_title, context=recognition_context
            )

            llm_response = llm_client.invoke([
                SystemMessage(content=DOC_META_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ])

            meta = self._parse_meta(llm_response.content)

            if not meta["subject"] or meta["subject"].upper() == "UNKNOWN":
                self.logger.info(f"LLM未识别出主题实体，降级使用标题: {file_title}")
                meta["subject"] = file_title

            self.logger.info(
                f"LLM抽取元数据: subject={meta['subject']}, doc_type={meta['doc_type']}, domain={meta['domain']}"
            )
            return meta
        except Exception as e:
            self.logger.error(f"LLM调用失败，降级使用标题: {file_title}，异常: {e}")
            return fallback

    @staticmethod
    def _parse_meta(raw: str) -> Dict[str, str]:
        """解析 LLM 输出的元数据 JSON，兼容缺失字段与非 JSON 输出。"""
        raw = (raw or "").strip()
        default = {"subject": "", "doc_type": "其他", "domain": "通用"}
        if not raw:
            return default
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    "subject": str(data.get("subject", "")).strip(),
                    "doc_type": str(data.get("doc_type", "其他")).strip() or "其他",
                    "domain": str(data.get("domain", "通用")).strip() or "通用",
                }
        except (JSONDecodeError, TypeError):
            # 非 JSON 输出，整体退化为主题字符串（兼容纯文本返回）
            pass
        default["subject"] = raw
        return default

    def _embedding_subject(self, subject) -> List[float]:
        try:
            dense_vectors = AIClients.embed([subject], text_type="document")
        except Exception as e:
            raise EmbeddingError(
                message=f"主题实体 [{subject}] 向量化失败", node_name=self.name, cause=e
            ) from e

        if not dense_vectors or not dense_vectors[0]:
            raise EmbeddingError(message=f"主题实体 [{subject}] 向量化结果为空", node_name=self.name)

        return dense_vectors[0]

    def _insert_milvus(self, file_title, subject, doc_type, domain,
                       dense_vector: List[float], subject_collection):
        try:
            milvus_client = StorageClients.get_milvus_client()

            if not milvus_client.has_collection(subject_collection):
                self._create_subject_collection(subject_collection, milvus_client)

            data = {
                "file_title": file_title,
                "subject": subject,
                "doc_type": doc_type,
                "domain": domain,
                "dense_vector": dense_vector,
            }
            result = milvus_client.insert(collection_name=subject_collection, data=[data])
            self.logger.info(f"已成功保存到 Milvus，ID: {result['ids'][0]}")
        except Exception as e:
            raise MilvusError(
                message=f"主题实体 [{subject}] 写入 Milvus 集合 [{subject_collection}] 失败",
                node_name=self.name, cause=e
            ) from e

    def _create_subject_collection(self, collection_name, milvus_client):
        metric_type = os.getenv("MILVUS_METRIC_TYPE", "COSINE")

        schema = milvus_client.create_schema()
        schema.add_field(field_name="pk", datatype=DataType.VARCHAR,
                         is_primary=True, auto_id=True, max_length=100)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="subject", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="doc_type", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="domain", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR,
                         dim=self.config.embedding_dim)

        index_param = milvus_client.prepare_index_params()
        index_param.add_index(field_name="dense_vector", index_name="dense_vector_index",
                              index_type="AUTOINDEX", metric_type=metric_type)

        milvus_client.create_collection(collection_name=collection_name,
                                        schema=schema, index_params=index_param)
        self.logger.info(f"集合 {collection_name} 创建成功并构建了索引")

    def _fill_meta(self, subject, doc_type, domain, state, chunks):
        for chunk in chunks:
            chunk['subject'] = subject
            chunk['doc_type'] = doc_type
            chunk['domain'] = domain

        state['subject'] = subject
        state['doc_type'] = doc_type
        state['domain'] = domain

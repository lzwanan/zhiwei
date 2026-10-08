#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SubjectRecognitionNode（文档元数据识别节点）单元测试

用途：通用化改造（item_name -> subject + doc_type + domain）后的回归测试。

特点：
- 全部离线运行，不触达百炼 LLM / Embedding / Milvus（用 unittest.mock 打桩）。
- 仅依赖标准库 unittest，无需 pytest。

运行方式（与项目内其他测试脚本一致，直接执行；失败时退出码非 0，可用于 CI）：
    python test/import_process/test_subject_recognition.py
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from processor.import_process.nodes.subject_recognition import SubjectRecognitionNode  # noqa: E402
from processor.import_process.exceptions import (  # noqa: E402
    StateFieldError,
    EmbeddingError,
    MilvusError,
)
from processor.import_process.state import create_default_state  # noqa: E402

MODULE = "processor.import_process.nodes.subject_recognition"

# 与 config.embedding_dim 对齐即可，长度不影响 mock 断言
FAKE_DENSE = [0.01] * 8


def _make_state(file_title="某文档", chunks=None):
    if chunks is None:
        chunks = [{"content": "这是文档的第一段正文内容，用于构造识别上下文。"}]
    return create_default_state(file_title=file_title, chunks=chunks)


def _fake_llm(content):
    """构造一个 mock 的 ChatOpenAI，invoke 返回带 .content 的响应。"""
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content=content)
    return llm


class TestParseMeta(unittest.TestCase):
    """_parse_meta：LLM 输出解析（纯函数，无需外部依赖）。"""

    def setUp(self):
        self.node = SubjectRecognitionNode()

    def test_valid_json(self):
        raw = json.dumps({"subject": "华为擎云 L420x", "doc_type": "操作手册", "domain": "产品"})
        meta = self.node._parse_meta(raw)
        self.assertEqual(meta, {"subject": "华为擎云 L420x", "doc_type": "操作手册", "domain": "产品"})

    def test_plain_text_fallback(self):
        meta = self.node._parse_meta("优利德 UT890D+ 万用表")
        self.assertEqual(meta["subject"], "优利德 UT890D+ 万用表")
        self.assertEqual(meta["doc_type"], "其他")
        self.assertEqual(meta["domain"], "通用")

    def test_empty_string(self):
        meta = self.node._parse_meta("")
        self.assertEqual(meta, {"subject": "", "doc_type": "其他", "domain": "通用"})

    def test_missing_fields_default(self):
        meta = self.node._parse_meta(json.dumps({"subject": "项目A"}))
        self.assertEqual(meta["subject"], "项目A")
        self.assertEqual(meta["doc_type"], "其他")
        self.assertEqual(meta["domain"], "通用")


class TestPrepareContext(unittest.TestCase):
    """_prepare_recognition_context：上下文构建与长度兜底。"""

    def setUp(self):
        self.node = SubjectRecognitionNode()

    def test_normal_join(self):
        chunks = [{"content": "AAA"}, {"content": "BBB"}]
        ctx = self.node._prepare_recognition_context(chunks, subject_chunk_k=3, subject_chunk_size=1000)
        self.assertIn("AAA", ctx)
        self.assertIn("BBB", ctx)
        self.assertEqual(ctx.count("【切片】"), 2)

    def test_respects_chunk_k(self):
        chunks = [{"content": str(i)} for i in range(5)]
        ctx = self.node._prepare_recognition_context(chunks, subject_chunk_k=2, subject_chunk_size=1000)
        self.assertEqual(ctx.count("【切片】"), 2)

    def test_first_chunk_too_long_truncated_not_empty(self):
        long_content = "X" * 500
        chunks = [{"content": long_content}]
        ctx = self.node._prepare_recognition_context(chunks, subject_chunk_k=3, subject_chunk_size=50)
        # 首个切片即超限时应截断保留，而非返回空串
        self.assertTrue(ctx)
        self.assertLessEqual(len(ctx), 50)


class TestValidateState(unittest.TestCase):
    """_validate_state：状态字段校验。"""

    def setUp(self):
        self.node = SubjectRecognitionNode()

    def test_missing_file_title(self):
        state = create_default_state(chunks=[{"content": "x"}], file_title="")
        with self.assertRaises(StateFieldError):
            self.node._validate_state(state)

    def test_missing_chunks(self):
        state = create_default_state(file_title="标题", chunks=[])
        with self.assertRaises(StateFieldError):
            self.node._validate_state(state)


class TestProcessEndToEnd(unittest.TestCase):
    """process 全流程（LLM/Embedding/Milvus 均打桩）。"""

    def setUp(self):
        self.node = SubjectRecognitionNode()
        self.milvus = MagicMock()
        self.milvus.has_collection.return_value = True
        self.milvus.insert.return_value = {"ids": ["123"]}

        # 打桩节点模块内引用的 AIClients / StorageClients（离线运行，不触网）
        self._stack = []
        self.mock_storage = self._start(patch(f"{MODULE}.StorageClients"))
        self.mock_ai = self._start(patch(f"{MODULE}.AIClients"))

        self.mock_storage.get_milvus_client.return_value = self.milvus
        self.mock_ai.embed.return_value = [FAKE_DENSE]

    def _start(self, patcher):
        mock = patcher.start()
        self._stack.append(patcher)
        return mock

    def tearDown(self):
        for p in self._stack:
            p.stop()

    def _captured_insert(self):
        self.milvus.insert.assert_called_once()
        _, kwargs = self.milvus.insert.call_args
        return kwargs["data"][0]

    def test_happy_path(self):
        self.mock_ai.get_subject_llm.return_value = _fake_llm(
            json.dumps({"subject": "员工差旅报销管理办法", "doc_type": "制度规范", "domain": "人事"})
        )
        state = _make_state(file_title="差旅办法")
        out = self.node.process(state)

        self.assertEqual(out["subject"], "员工差旅报销管理办法")
        self.assertEqual(out["doc_type"], "制度规范")
        self.assertEqual(out["domain"], "人事")
        # chunk 回填
        self.assertEqual(out["chunks"][0]["subject"], "员工差旅报销管理办法")
        self.assertEqual(out["chunks"][0]["doc_type"], "制度规范")
        # Milvus 写入字段
        row = self._captured_insert()
        self.assertEqual(set(row.keys()), {"file_title", "subject", "doc_type", "domain", "dense_vector"})
        self.assertEqual(row["subject"], "员工差旅报销管理办法")

    def test_unknown_subject_falls_back_to_title(self):
        self.mock_ai.get_subject_llm.return_value = _fake_llm(
            json.dumps({"subject": "UNKNOWN", "doc_type": "其他", "domain": "通用"})
        )
        out = self.node.process(_make_state(file_title="无法识别的文档"))
        self.assertEqual(out["subject"], "无法识别的文档")

    def test_llm_exception_falls_back(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("网络错误")
        self.mock_ai.get_subject_llm.return_value = llm

        out = self.node.process(_make_state(file_title="标题兜底"))
        self.assertEqual(out["subject"], "标题兜底")
        self.assertEqual(out["doc_type"], "其他")
        self.assertEqual(out["domain"], "通用")
        # 降级后仍应完成写入
        self.milvus.insert.assert_called_once()

    def test_embedding_error_raises(self):
        self.mock_ai.get_subject_llm.return_value = _fake_llm(
            json.dumps({"subject": "主题", "doc_type": "其他", "domain": "通用"})
        )
        self.mock_ai.embed.return_value = [[]]  # 空向量
        with self.assertRaises(EmbeddingError):
            self.node.process(_make_state())

    def test_milvus_insert_error_raises(self):
        self.mock_ai.get_subject_llm.return_value = _fake_llm(
            json.dumps({"subject": "主题", "doc_type": "其他", "domain": "通用"})
        )
        self.milvus.insert.side_effect = RuntimeError("写库失败")
        with self.assertRaises(MilvusError):
            self.node.process(_make_state())


if __name__ == "__main__":
    unittest.main(verbosity=2)

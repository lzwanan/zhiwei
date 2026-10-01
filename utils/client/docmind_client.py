"""
阿里云 DocMind 智能文档解析客户端（POP 通道）

将 PDF / Word / PPT 等文档解析为结构化 Markdown。
底层调用文档解析（大模型版）异步三段式接口：
    SubmitDocParserJob(Advance)  ->  QueryDocParserStatus  ->  GetDocParserResult

沿用 BaseClientManager 的双重检查锁 + 环境变量校验范式，缓存底层 SDK 客户端。
"""
import os
import threading
import time
from pathlib import Path
from typing import Optional

from alibabacloud_docmind_api20220711.client import Client as DocMindClientCore
from alibabacloud_docmind_api20220711 import models as docmind_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from utils.client.base import BaseClientManager, logger

# 任务状态常量
_STATUS_SUCCESS = "success"
_STATUS_FAIL = "fail"


def _to_dict(obj) -> dict:
    """把 SDK 返回对象/Map 兼容地转成 dict"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    to_map = getattr(obj, "to_map", None)
    if callable(to_map):
        return to_map() or {}
    return {}


def _pick(data: dict, *names: str):
    """
    从 dict 中大小写无关地取第一个命中的 key

    DocMind 不统一：提交/状态接口经 to_map() 产出 PascalCase（Id/Status），
    结果接口 data 为原始 JSON 的 camelCase（layoutParsingResults）。
    这里做大小写不敏感查找，避免破坏图片路径等大小写敏感的 value。
    """
    if not isinstance(data, dict):
        return None
    for n in names:
        if n in data:
            return data[n]
    lower_map = {k.lower(): k for k in data if isinstance(k, str)}
    for n in names:
        k = lower_map.get(n.lower())
        if k is not None:
            return data[k]
    return None


class DocMindClient(BaseClientManager):
    """
    DocMind 文档解析客户端

    职责：提交解析任务 -> 轮询状态 -> 拉取并拼接 Markdown 结果。
    底层 SDK 客户端全局复用一个（无状态、线程安全），
    每次解析参数（增强模式/超时等）通过实例字段传入。
    """

    _sdk_client: Optional[DocMindClientCore] = None
    _sdk_lock = threading.Lock()

    def __init__(
        self,
        enhancement_mode: str = "AUTO",
        llm_enhancement: bool = False,
        poll_interval: int = 5,
        timeout: int = 600,
        layout_step_size: int = 200,
    ):
        """
        Args:
            enhancement_mode: 增强模式 AUTO/VLM/LLM/DIGITAL/OCR
            llm_enhancement:  是否开启 LLM 内容增强
            poll_interval:    状态轮询间隔（秒）
            timeout:          单个文档解析超时（秒）
            layout_step_size: 结果分页拉取步长
        """
        self.enhancement_mode = enhancement_mode
        self.llm_enhancement = llm_enhancement
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.layout_step_size = layout_step_size

    # ------------------------------------------------------------------ #
    # 底层 SDK 客户端（类级缓存，双重检查锁）
    # ------------------------------------------------------------------ #
    @classmethod
    def get_sdk_client(cls) -> DocMindClientCore:
        return cls._get_or_create("_sdk_client", cls._sdk_lock, cls._create_sdk_client)

    @classmethod
    def _create_sdk_client(cls) -> DocMindClientCore:
        try:
            access_key_id = cls._require_env("DOCMIND_ACCESS_KEY_ID")
            access_key_secret = cls._require_env("DOCMIND_ACCESS_KEY_SECRET")
            endpoint = os.getenv("DOCMIND_ENDPOINT", "docmind-api.cn-hangzhou.aliyuncs.com")

            config = open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
            )
            config.endpoint = endpoint
            client = DocMindClientCore(config)
            logger.info(f"DocMind 客户端创建成功: {endpoint}")
            return client
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"DocMind 客户端创建失败: {e}")
            raise ConnectionError(f"DocMind 客户端创建失败: {e}") from e

    # ------------------------------------------------------------------ #
    # 对外主方法
    # ------------------------------------------------------------------ #
    def parse_to_markdown(self, file_path: Path) -> str:
        """
        解析单个文档为 Markdown 文本

        Args:
            file_path: 本地文档路径（pdf/doc/ppt/xls/图片等）

        Returns:
            拼接后的 Markdown 文本
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"待解析文件不存在: {file_path}")

        job_id = self._submit_job(file_path)
        logger.info(f"DocMind 任务已提交: id={job_id}")

        self._wait_until_done(job_id)
        markdown = self._fetch_markdown(job_id)
        logger.info(f"DocMind 解析完成: id={job_id}, markdown 长度={len(markdown)}")
        return markdown

    # ------------------------------------------------------------------ #
    # 步骤一：提交异步解析任务（本地文件上传）
    # ------------------------------------------------------------------ #
    def _submit_job(self, file_path: Path) -> str:
        client = self.get_sdk_client()
        file_name = file_path.name
        file_ext = file_path.suffix.lstrip(".").lower() or None

        # EnhancementMode 目前仅支持 VLM，且必须配合 LLMEnhancement=True 才生效；
        # AUTO/BASE/空 一律走基础解析链路（不传 enhancement_mode）。
        mode = (self.enhancement_mode or "").strip().upper()
        use_vlm = mode == "VLM"

        request = docmind_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=open(file_path, "rb"),
            file_name=file_name,
            file_name_extension=file_ext,
            llm_enhancement=True if use_vlm else self.llm_enhancement,
            enhancement_mode="VLM" if use_vlm else None,
        )
        runtime = util_models.RuntimeOptions(
            connect_timeout=10000,
            read_timeout=self.timeout * 1000,
        )
        try:
            response = client.submit_doc_parser_job_advance(request, runtime)
            data = _to_dict(response.body.data)
            job_id = _pick(data, "id", "Id")
            if not job_id:
                raise RuntimeError(f"DocMind 提交任务未返回任务 ID: {data}")
            return job_id
        except Exception as e:
            self._raise_if_has_message(e)
            raise RuntimeError(f"DocMind 提交任务失败: {e}") from e

    # ------------------------------------------------------------------ #
    # 步骤二：轮询任务状态
    # ------------------------------------------------------------------ #
    def _wait_until_done(self, job_id: str) -> None:
        client = self.get_sdk_client()
        deadline = time.time() + self.timeout

        while time.time() < deadline:
            request = docmind_models.QueryDocParserStatusRequest(id=job_id)
            try:
                response = client.query_doc_parser_status(request)
                data = _to_dict(response.body.data)
            except Exception as e:
                self._raise_if_has_message(e)
                raise RuntimeError(f"DocMind 查询状态失败: {e}") from e

            status = str(_pick(data, "status", "Status") or "").lower()
            if status == _STATUS_SUCCESS:
                return
            if status == _STATUS_FAIL:
                raise RuntimeError(f"DocMind 解析任务失败: {_pick(data, 'message', 'Message') or status}")

            processed = _pick(data, "numberOfSuccessfulParsing", "number_of_successful_parsing")
            logger.info(f"DocMind 解析中... 已处理模块数={processed}, 状态={status or 'processing'}")
            time.sleep(self.poll_interval)

        raise TimeoutError(f"DocMind 解析超时（>{self.timeout}s）: id={job_id}")

    # ------------------------------------------------------------------ #
    # 步骤三：分页拉取并拼接 Markdown 结果
    # ------------------------------------------------------------------ #
    def _fetch_markdown(self, job_id: str) -> str:
        client = self.get_sdk_client()
        parts: list[str] = []
        layout_num = 0
        # 防御性上限，避免异常情况下无限翻页
        max_pages = 10_000

        while layout_num < max_pages:
            request = docmind_models.GetDocParserResultRequest(
                id=job_id,
                layout_step_size=self.layout_step_size,
                layout_num=layout_num,
            )
            try:
                response = client.get_doc_parser_result(request)
                data = _to_dict(response.body.data)
            except Exception as e:
                self._raise_if_has_message(e)
                raise RuntimeError(f"DocMind 获取结果失败: {e}") from e

            page_md, page_count = self._extract_markdown(data)
            if page_md:
                parts.append(page_md)

            # 无新增数据则结束
            if not page_count:
                break
            layout_num += page_count

            # 若返回数量小于步长，说明已是最后一页
            if page_count < self.layout_step_size:
                break

        markdown = "\n\n".join(p for p in parts if p).strip()
        if not markdown:
            raise RuntimeError(f"DocMind 未解析出任何 Markdown 内容: id={job_id}")
        return markdown

    @staticmethod
    def _extract_markdown(data: dict) -> tuple[str, int]:
        """
        从结果 data 中提取 Markdown 文本

        兼容两种返回结构：
          1. 实测结构：{"layouts": [{"markdownContent": "...", "text": "..."}, ...]}
          2. 文档所述：{"layoutParsingResults": [{"markdown": {"text": "..."}}, ...]}

        Returns:
            (本页 markdown 文本, 本页返回的条目数量)
        """
        # 结构 1：layouts（实际 GetDocParserResult 返回）
        layouts = _pick(data, "layouts")
        if isinstance(layouts, list) and layouts:
            texts = []
            for item in layouts:
                if not isinstance(item, dict):
                    continue
                md = _pick(item, "markdownContent", "markdown_content", "text")
                if isinstance(md, str):
                    texts.append(md)
            return "".join(texts), len(layouts)

        # 结构 2：layoutParsingResults
        results = _pick(data, "layoutParsingResults", "layout_parsing_results")
        if isinstance(results, list) and results:
            texts = []
            for item in results:
                md = _pick(item, "markdown") if isinstance(item, dict) else None
                if isinstance(md, dict):
                    texts.append(_pick(md, "text") or "")
                elif isinstance(md, str):
                    texts.append(md)
            return "\n\n".join(t for t in texts if t), len(results)

        md = _pick(data, "markdown")
        if isinstance(md, dict):
            return _pick(md, "text") or "", 1
        if isinstance(md, str):
            return md, 1

        return "", 0

    @staticmethod
    def _raise_if_has_message(error: Exception) -> None:
        """阿里云 SDK 的 TeaException 把详细信息放在 .message / .data 里，尽量透出"""
        message = getattr(error, "message", None)
        if message:
            data = getattr(error, "data", None)
            raise RuntimeError(f"{message} | detail={data}") from error

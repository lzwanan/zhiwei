import logging
import threading
from typing import Optional

import oss2
from dotenv import load_dotenv
from pymilvus import MilvusClient
from pymongo import MongoClient
from pymongo.database import Database
from utils.client.base import BaseClientManager

logger = logging.getLogger(__name__)
load_dotenv()


class StorageClients(BaseClientManager):
    """
    存储类客户端：阿里云 OSS  Milvus
    """

    _oss_client: Optional["oss2.Bucket"] = None
    _oss_lock = threading.Lock()

    @classmethod
    def get_oss_client(cls) -> "oss2.Bucket":
        return cls._get_or_create("_oss_client", cls._oss_lock, cls._create_oss)

    @classmethod
    def _create_oss(cls) -> "oss2.Bucket":
        try:
            endpoint = cls._require_env("OSS_ENDPOINT")
            access_key_id = cls._require_env("OSS_ACCESS_KEY_ID")
            access_key_secret = cls._require_env("OSS_ACCESS_KEY_SECRET")
            bucket_name = cls._require_env("OSS_BUCKET_NAME")

            auth = oss2.Auth(access_key_id, access_key_secret)
            bucket = oss2.Bucket(auth, endpoint, bucket_name)

            # OSS 桶需在控制台预先创建，这里只做存在校验（不自动建桶）
            try:
                bucket.get_bucket_info()
                logger.info(f"存储桶已存在:{bucket_name}")
            except oss2.exceptions.NoSuchBucket:
                raise ConnectionError(f"OSS 存储桶不存在，请先在控制台创建:{bucket_name}")

            logger.info(f"阿里云 OSS 配置完成")
            return bucket
        except EnvironmentError:
            raise  # 配置缺失，直接上抛
        except ConnectionError:
            raise  # 桶不存在，直接上抛
        except Exception as e:
            logger.error(f"阿里云 OSS 客户端初始化失败:{e}")
            raise ConnectionError(f"阿里云 OSS 配置错误:{e}") from e  # from e 保留原始异常的堆栈跟踪信息

    """
     存储类客户端：Milvus
     """

    _milvus_client: Optional[MilvusClient] = None
    _milvus_lock = threading.Lock()

    @classmethod
    def get_milvus_client(cls) -> MilvusClient:
        return cls._get_or_create("_milvus_client", cls._milvus_lock, cls._create_milvus_client)

    @classmethod
    def _create_milvus_client(cls) -> MilvusClient:
        try:
            milvus_uri = cls._require_env("MILVUS_URL")

            client = MilvusClient(milvus_uri)

            return client
        except EnvironmentError:
            raise  # 配置缺失，直接上抛
        except Exception as e:
            logger.error(f"Milvus 客户端初始化失败:{e}")
            raise ConnectionError(f"Milvus 连接:{e}") from e  # from e 保留原始异常的堆栈跟踪信息


    # ── MongoDB ──

    _mongo_db: Optional[Database] = None
    _mongo_lock = threading.Lock()

    @classmethod
    def get_mongo_db(cls) -> Database:
        return cls._get_or_create("_mongo_db", cls._mongo_lock, cls._create_mongo_db)

    @classmethod
    def _create_mongo_db(cls) -> Database:
        try:
            mongo_url = cls._require_env("MONGO_URL")
            db_name = cls._require_env("MONGO_DB_NAME")

            # 1. 实例化客户端
            client = MongoClient(mongo_url)

            # 2. 根据客户端获取数据库对象
            db = client[db_name]

            logger.info(f"MongoDB 客户端初始化成功 (db={db_name})")

            # 3. 返回数据库对象
            return db
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error(f"MongoDB 客户端创建失败: {e}")
            raise ConnectionError(f"MongoDB 连接失败: {e}") from e

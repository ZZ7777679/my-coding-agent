"""单写者元数据存储，限制读取大小并原子替换单个文件。

Single-writer metadata storage with bounded reads and atomic single-file replacement.
"""

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import portalocker
from pydantic import BaseModel, ValidationError

from my_agent.config import (
    DataLocation,
    ModelConfig,
    default_config_text,
    load_config,
    model_config_text,
)
from my_agent.errors import AgentError
from my_agent.models.connections import ConnectionSettings
from my_agent.rpc.dto import DTO, ModelId, StorageInfo, Timestamp
from my_agent.runtime.settings import RunLimits


def utc_now() -> str:
    """生成带 UTC 标识的时间文本，供持久化记录与公开 DTO 使用。

    Produce a UTC timestamp for persisted records and public DTOs.
    """

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class StorageMetadata(DTO):
    """记录数据格式版本与首次初始化时间。

    Record the data format version and first initialization time.
    """

    schema_version: int
    initialized_at: Timestamp


def read_document[T: BaseModel](path: Path, model: type[T]) -> T:
    """有界读取并严格解析数据文件；损坏时不返回空记录。

    Read and validate a bounded data file; never replace corruption with empty records.
    """

    try:
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise AgentError("DATA_INVALID", "应用记录超过大小限制。")
        return model.model_validate_json(raw)
    except (ValidationError, UnicodeError) as exc:
        raise AgentError(
            "DATA_INVALID", "应用记录已损坏或格式不受支持，请保留文件并检查备份。"
        ) from exc
    except OSError as exc:
        raise AgentError("DATA_UNAVAILABLE", "无法读取应用记录。") from exc


def atomic_write(path: Path, content: str) -> None:
    """在同目录写入、同步并替换单个文件；失败时清理自有临时文件。

    Write, sync and replace one file in its directory; clean up only the owned temporary file.
    """

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix="." + path.name + "-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise AgentError("DATA_DIR_NOT_WRITABLE", "保存失败，已有记录已保留。") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # 清理失败不覆盖原写入错误，仅记录固定公开码。
                # Keep the original write failure and emit only a fixed public cleanup code.
                logging.getLogger(__name__).warning("DATA_TEMP_CLEANUP_FAILED")


def write_document(path: Path, value: BaseModel) -> None:
    """以 UTF-8 JSON 原子保存经校验的对象。

    Atomically persist a validated object as UTF-8 JSON.
    """

    atomic_write(
        path, json.dumps(value.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )


class Storage:
    """管理一个数据根及当前实例的写入锁；不提供跨文件事务。

    Manage a data root and this instance's writer lock, without cross-file transactions.
    """

    def __init__(self, location: DataLocation) -> None:
        """绑定已解析的数据根，延迟所有文件创建和锁获取。

        Bind the resolved data root, deferring file creation and lock acquisition.
        """

        self.location = location
        self.root = location.root
        self.writing = False

    @property
    def metadata_path(self) -> Path:
        """返回本数据根内的格式元数据位置。

        Return the format metadata location within this data root.
        """

        return self.root / "storage.json"

    def validate_metadata(self) -> None:
        """拒绝不支持的数据版本，保留已有元数据供恢复。

        Reject unsupported data versions while preserving metadata for recovery.
        """

        if self.metadata_path.exists():
            metadata = read_document(self.metadata_path, StorageMetadata)
            if metadata.schema_version != 1:
                raise AgentError(
                    "DATA_VERSION_UNSUPPORTED", "应用数据版本不受支持，请使用兼容版本。"
                )

    @contextmanager
    def writer(self) -> Iterator["Storage"]:
        """非阻塞获取独占锁并验证存储；正常退出或异常时均释放。

        Acquire an exclusive lock without waiting, validate storage and release on every exit.
        """

        if self.writing:
            raise AgentError("DATA_DIR_BUSY", "当前服务已持有写入锁。")
        try:
            if shutil.disk_usage(self.root.anchor).free < 1024 * 1024:
                raise AgentError("DISK_FULL", "应用数据盘可用空间不足。")
            self.root.mkdir(parents=True, exist_ok=True)
            with portalocker.Lock(
                self.root / ".runtime.lock",
                mode="a+b",
                timeout=0,
                flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
            ):
                self.writing = True
                try:
                    self.validate_metadata()
                    load_config(self.location)
                    yield self
                finally:
                    self.writing = False
        except portalocker.exceptions.LockException as exc:
            raise AgentError(
                "DATA_DIR_BUSY", "数据目录已被另一个实例使用。", "关闭占用该目录的应用。"
            ) from exc
        except OSError as exc:
            raise AgentError("DATA_DIR_NOT_WRITABLE", "无法写入所选应用数据目录。") from exc

    def require_writer(self) -> None:
        """在任何写入前确认当前实例持锁。

        Require this instance to hold the lock before a write.
        """

        if not self.writing:
            raise AgentError("WRITER_REQUIRED", "此操作需要应用数据写入锁。")

    def initialize(self) -> None:
        """仅补齐缺失的元数据和配置，不覆盖已有文件。

        Create only missing metadata and configuration, preserving existing files.
        """

        self.require_writer()
        self.validate_metadata()
        load_config(self.location)
        # 多个文件分别原子写入，不构成事务；重试只补齐缺失文件。
        # Files are individually atomic, not transactional; retries create only missing files.
        if not self.metadata_path.exists():
            write_document(
                self.metadata_path, StorageMetadata(schema_version=1, initialized_at=utc_now())
            )
        config_path = self.root / "config.toml"
        if not config_path.exists():
            atomic_write(config_path, default_config_text())

    def busy(self) -> bool:
        """只读探测其他写入者；当前实例已持锁时不报告自身冲突。

        Probe other writers read-only, without reporting this instance's own lock as a conflict.
        """

        if self.writing:
            return False
        path = self.root / ".runtime.lock"
        if not path.exists():
            return False
        try:
            with path.open("rb") as stream:
                portalocker.lock(stream, portalocker.LOCK_EX | portalocker.LOCK_NB)
                portalocker.unlock(stream)
            return False
        except portalocker.exceptions.LockException:
            return True
        except OSError as exc:
            raise AgentError("ENVIRONMENT_RESTRICTED", "无法检查应用写入锁。") from exc

    def save_model(self, model_id: ModelId, run: RunLimits | None = None) -> None:
        """持锁修改默认模型，保留其他已验证配置并原子保存。

        Update the default model under the lock, preserving other validated settings atomically.
        """

        self.require_writer()
        current = load_config(self.location)
        updated = ModelConfig.model_validate({**current.model.model_dump(), "model_id": model_id})
        self.initialize()
        atomic_write(current.path, model_config_text(updated, run or current.run, current.http))

    def save_connections(self, settings: ConnectionSettings) -> None:
        """原子保存连接设置，同时保留模型与运行预算。 Save connection settings atomically."""
        self.require_writer()
        current = load_config(self.location)
        atomic_write(current.path, model_config_text(current.model, current.run, settings))

    def info(self) -> StorageInfo:
        """返回公开存储状态；不初始化目录或篡改记录。

        Return public storage status without initializing directories or changing records.
        """

        self.validate_metadata()
        return StorageInfo(
            data_dir=str(self.root),
            source=self.location.source,
            data_schema_version=1,
            status="busy"
            if self.busy()
            else ("ready" if self.metadata_path.exists() else "not_initialized"),
        )

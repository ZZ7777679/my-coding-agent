"""显式装配共享会话核心。 Explicit composition of the shared session core."""

from my_agent.config import DEFAULTS, MODEL_DEFAULTS, load_config
from my_agent.credentials import ResolvedCredential, resolve_credential
from my_agent.models.go import GoClient
from my_agent.models.http import ModelHttpPool
from my_agent.projects import ProjectService
from my_agent.sessions.service import SessionService
from my_agent.sessions.store import SessionStore
from my_agent.storage import Storage
from my_agent.worker import BusinessWorker


def build_model_http() -> ModelHttpPool:
    """集中装配连接清理默认值，不探测或覆盖用户网络。

    Compose pooled HTTP defaults without detecting or overriding user networking.
    """
    http = ModelHttpPool(
        reuse_enabled=DEFAULTS["http"]["reuse_enabled"],
        keepalive_expiry=DEFAULTS["http"]["keepalive_expiry_seconds"],
        drain_timeout_seconds=DEFAULTS["http"]["response_drain_timeout_seconds"],
    )
    return http


def build_sessions(
    storage: Storage,
    worker: BusinessWorker,
    credential: ResolvedCredential,
    *,
    http: ModelHttpPool | None = None,
) -> SessionService:
    """入口持锁后注入生产组件；用户环境凭据可在新运行前刷新。

    Inject production components after entry-point locking; refresh user credentials per run.
    """
    if http is None:
        http = build_model_http()
        http.reuse_enabled = load_config(storage.location).http.reuse_enabled
    shared_http = http

    def model_factory() -> GoClient:
        """进程凭据优先保持，其他来源按既定规则刷新。

        Preserve process credentials, refresh other sources.
        """
        current = credential if credential.info.source == "process" else resolve_credential()
        return GoClient(current, str(MODEL_DEFAULTS["base_url"]), shared_http)

    return SessionService(
        SessionStore(storage),
        ProjectService(storage),
        worker,
        model_factory,
        close_model=shared_http.close,
    )

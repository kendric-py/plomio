from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from core.configs import LivenessConfig, RedisConfig

# Load this app's .env into the real process environment, independent of cwd — mirrors
# apps/api/src/config.py, needed because this worker can be launched from outside its own
# directory (e.g. by an orchestrator) and every *Config class below builds itself at import time.
ENV_FILE = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=ENV_FILE)


class ProxyApiConfig(BaseSettings):
    """Placeholder client config for the future proxy-issuing API endpoint — the endpoint
    does not exist yet, so ISSUE_URL is empty by default and get_proxy() returns None until
    it's configured, without the rest of the worker treating that as an error."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='PROXY_API_',
        extra='ignore',
    )

    ISSUE_URL: str = Field(default='')
    TOKEN: str = Field(default='')
    TIMEOUT_SECONDS: float = Field(default=60.0)


class GenerationConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='GENERATION_',
        extra='ignore',
    )

    CONCURRENCY_PER_MARKETPLACE: int = Field(default=1)
    MAX_SESSIONS_PER_PROXY: int = Field(default=20)
    TARGET_POOL_DEPTH: int = Field(default=10)
    # False only for local dev, where there's no proxy API yet (see ProxyApiConfig) — generates
    # sessions with a direct connection instead of blocking forever on WAITING_FOR_PROXY.
    # Must stay True anywhere real, since marketplaces ban IPs generating sessions without proxies.
    REQUIRE_PROXY: bool = Field(default=True)
    TTL_MS: int = Field(default=7 * 60 * 1000)  # a bit under the ~10-20min natural session lifetime
    VALIDATION_TIMEOUT_SECONDS: float = Field(default=15.0)
    # Above the worst case inside _run_browser (30s goto + 60s cookie-poll + ~4s sleeps) with
    # margin. Bounds a hung Camoufox launch/teardown so it can't block an executor thread forever.
    BROWSER_ATTEMPT_TIMEOUT_S: float = Field(default=120.0)
    NO_PROXY_RETRY_DELAY_SECONDS: float = Field(default=30.0)
    POOL_FULL_RECHECK_DELAY_SECONDS: float = Field(default=15.0)


class SessionsStreamConfig(BaseSettings):
    """Naming for the per-marketplace Redis Stream (`{PREFIX}:{marketplace}`, e.g.
    `sessions:ozon`) that `SessionPoolStore` (packages/sessions) publishes to alongside the TTL'd
    HSET/ZSET pool — a separate, explicitly-named channel so other future domains sharing the same
    Redis instance don't collide with session data. See apps/worker_sessions/AGENTS.md."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='SESSIONS_STREAM_',
        extra='ignore',
    )

    PREFIX: str = Field(default='sessions')
    # Approximate cap (XADD MAXLEN ~) so a lagging/absent consumer can't grow the stream
    # unboundedly — the pool's real source of truth stays the TTL'd HSET/ZSET, not the stream.
    MAXLEN: int = Field(default=1000)


class Socks5TunnelConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='SOCKS5_TUNNEL_',
        extra='ignore',
    )

    MAX_GLOBAL_CONNECTIONS: int = Field(default=512)
    MAX_PER_TUNNEL_CONNECTIONS: int = Field(default=128)
    CLIENT_HANDSHAKE_TIMEOUT_S: float = Field(default=15.0)
    UPSTREAM_CONNECT_TIMEOUT_S: float = Field(default=10.0)
    PIPE_IDLE_TIMEOUT_S: float = Field(default=60.0)
    LISTEN_BACKLOG: int = Field(default=128)
    STOP_DRAIN_TIMEOUT_S: float = Field(default=5.0)
    ERROR_LOG_THROTTLE_WINDOW_S: float = Field(default=5.0)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=10)
    CIRCUIT_BREAKER_WINDOW_S: float = Field(default=10.0)
    CIRCUIT_BREAKER_COOLDOWN_S: float = Field(default=20.0)


class ProcessReaperConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='PROCESS_REAPER_',
        extra='ignore',
    )

    SCAN_INTERVAL_S: float = Field(default=60.0)
    # A healthy session finishes in ~1-2 min; 5 min is a safe margin before it's orphaned garbage.
    MAX_AGE_S: float = Field(default=300.0)
    SIGTERM_GRACE_S: float = Field(default=5.0)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore',
    )

    DEBUG: bool = Field(default=False)

    REDIS: RedisConfig = Field(default_factory=RedisConfig)
    PROXY_API: ProxyApiConfig = Field(default_factory=ProxyApiConfig)
    GENERATION: GenerationConfig = Field(default_factory=GenerationConfig)
    SESSIONS_STREAM: SessionsStreamConfig = Field(default_factory=SessionsStreamConfig)
    SOCKS5_TUNNEL: Socks5TunnelConfig = Field(default_factory=Socks5TunnelConfig)
    PROCESS_REAPER: ProcessReaperConfig = Field(default_factory=ProcessReaperConfig)
    LIVENESS: LivenessConfig = Field(default_factory=LivenessConfig)


config = Config()

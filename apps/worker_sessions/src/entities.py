# `ProxyConfig`/`SessionMessage` moved to packages/sessions (shared Redis wire contract with
# apps/worker_parser) — see packages/sessions/AGENTS.md. Re-exported here so existing imports of
# `apps.worker_sessions.src.entities` keep working unchanged.
from packages.sessions.src.entities import ProxyConfig, SessionMessage  # noqa: F401

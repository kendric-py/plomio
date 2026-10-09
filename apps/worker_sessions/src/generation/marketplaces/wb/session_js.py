import atexit
import logging
import threading
import time

from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.exceptions import JsRuntimeError
from apps.worker_sessions.src.generation.js_runtime.loader import load_flow_module
from apps.worker_sessions.src.generation.marketplaces.wb.constants import (
    WB_FALLBACK_SPA_VERSION,
    WB_REQUIRED_COOKIES,
)
from apps.worker_sessions.src.generation.marketplaces.wb.utils import generate_device_id
from core.enums import Marketplace

logger = logging.getLogger(__name__)

wb_flow_warm = load_flow_module('wb', 'wb_flow_warm')

# Firefox 135 identity of the js_runtime flow (user-agent + TLS profile). Consumers must reuse it.
WB_JS_IMPERSONATE = 'firefox135'

# NodeSolver talks over a single stdin/stdout pipe, so every generator thread gets its own.
_local = threading.local()
_solvers: list = []
_solvers_lock = threading.Lock()


def _get_solver():
    solver = getattr(_local, 'solver', None)
    if solver is not None and solver.p.poll() is not None:
        _drop_solver(solver)  # dead process: release its pipes and reap it
        solver = None
    if solver is None:
        solver = wb_flow_warm.NodeSolver()
        _local.solver = solver
        with _solvers_lock:
            _solvers.append(solver)
    return solver


def _drop_solver(solver) -> None:
    solver.close()
    _local.solver = None
    with _solvers_lock:
        if solver in _solvers:
            _solvers.remove(solver)


def _close_all() -> None:
    for solver in _solvers:
        try:
            solver.close()
        except Exception:  # noqa: BLE001, S110 — best-effort at interpreter exit
            pass


atexit.register(_close_all)


def build_session_message(proxy: ProxyConfig | None) -> SessionMessage:
    start = time.monotonic()
    solver = _get_solver()
    try:
        result = wb_flow_warm.get_token(
            solver, proxy=proxy.to_curl_url() if proxy else None, impersonate=WB_JS_IMPERSONATE,
        )
    except Exception as exc:
        # A dead/hung solver must not poison the next attempt on this thread.
        _drop_solver(solver)
        raise JsRuntimeError(f'wb js_runtime failed: {exc}') from exc
    token = result.get('token')
    if not token:
        raise JsRuntimeError(f'wb js_runtime returned no token: {str(result.get("resp"))[:300]}')
    cookies = {**(result.get('cookies') or {}), 'x_wbaas_token': token}
    if not WB_REQUIRED_COOKIES <= cookies.keys():
        raise JsRuntimeError(f'wb js_runtime missing cookies: {sorted(cookies)}')
    logger.info(
        '[session_init] wb js_runtime elapsed=%.2fs solve=%.2fs',
        time.monotonic() - start, result.get('solve_s', 0.0),
    )
    return SessionMessage(
        marketplace=Marketplace.WILDBERRIES,
        proxy=proxy,
        cookies=cookies,
        user_agent=wb_flow_warm.UA,
        sec_ch_ua='',
        sec_ch_ua_platform='',
        extra={
            'device_id': generate_device_id(),
            # The browserless flow never loads the SPA, so the version can't be read from it.
            'spa_version': WB_FALLBACK_SPA_VERSION,
            'impersonate': WB_JS_IMPERSONATE,
        },
    )

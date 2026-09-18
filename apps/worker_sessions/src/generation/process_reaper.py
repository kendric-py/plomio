import asyncio
import logging
import time

import psutil

from apps.worker_sessions.src.config import config

logger = logging.getLogger(__name__)

# Substrings identifying the child processes Camoufox/Playwright spawn per browser session:
# the playwright Node driver and the Firefox (camoufox) binary and its content processes.
# When AsyncCamoufox loses track of a browser (crash/timeout during __aenter__, or a hung
# teardown), the process on the other end of that relationship is never closed and keeps
# running. A healthy session finishes in ~1-2 minutes, so anything with this cmdline older
# than MAX_AGE_S is orphaned garbage, not a live session.
_TARGET_CMDLINE_MARKERS = ('run-driver', 'camoufox-bin')


def _matches_target(process: psutil.Process) -> bool:
    try:
        cmdline = ' '.join(process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    return any(marker in cmdline for marker in _TARGET_CMDLINE_MARKERS)


def _reap_once(max_age_s: float, sigterm_grace_s: float) -> int:
    now = time.time()
    stale: list[psutil.Process] = []
    for process in psutil.process_iter(['pid', 'create_time']):
        try:
            if now - process.info['create_time'] < max_age_s:
                continue
            if not _matches_target(process=process):
                continue
            stale.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not stale:
        return 0

    for process in stale:
        try:
            logger.warning(
                '[process_reaper] event=killing_stale_process pid=%d age_s=%.0f cmd=%s',
                process.pid, now - process.info['create_time'], ' '.join(process.cmdline()),
            )
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _gone, alive = psutil.wait_procs(stale, timeout=sigterm_grace_s)
    for process in alive:
        try:
            logger.warning('[process_reaper] event=force_killing_pid pid=%d', process.pid)
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return len(stale)


async def run_process_reaper() -> None:
    """Background safety net: periodically kills orphaned Camoufox/Playwright driver and
    browser processes left behind by browser-init crashes. Runs forever alongside the
    generator workers; never raises."""
    reaper_config = config.PROCESS_REAPER
    loop = asyncio.get_running_loop()
    while True:
        try:
            reaped = await loop.run_in_executor(
                None, _reap_once, reaper_config.MAX_AGE_S, reaper_config.SIGTERM_GRACE_S,
            )
            if reaped:
                logger.warning('[process_reaper] event=reap_complete count=%d', reaped)
        except Exception:
            logger.exception('[process_reaper] event=reap_cycle_error')
        await asyncio.sleep(reaper_config.SCAN_INTERVAL_S)

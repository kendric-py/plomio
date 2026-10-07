import importlib
import sys
from pathlib import Path
from types import ModuleType

# apps/worker_sessions/js_runtime/ready — the browserless flow lives next to the app, not under src/
JS_RUNTIME_READY_DIR = Path(__file__).resolve().parents[3] / 'js_runtime' / 'ready'


def load_flow_module(marketplace_dir: str, module_name: str) -> ModuleType:
    """Imports a js_runtime flow module (`oz_flow`, `wb_flow_warm`, ...). The flows import each
    other as top-level modules (`from wb_flow import ...`), so their folder has to be on sys.path
    first — which is why this can't be a plain `import` statement. Call it at module level."""
    path = str(JS_RUNTIME_READY_DIR / marketplace_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(module_name)

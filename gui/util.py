import yaml
from pathlib import Path

# gui/util.py → parent = gui/ → parent.parent = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_config(path: str = None) -> dict:
    if path is None:
        path = _PROJECT_ROOT / "config.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)
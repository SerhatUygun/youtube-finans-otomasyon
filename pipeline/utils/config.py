import yaml
from pipeline.utils.paths import ROOT

_CONFIG_CACHE = None


def load_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f)
    return _CONFIG_CACHE

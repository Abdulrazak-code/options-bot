import os
import sys


def _reload_config(overrides: dict):
    for k, v in overrides.items():
        os.environ[k] = v
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config


def test_placeholder():
    assert True


def test_defaults():
    cfg = _reload_config({
        "MAX_LOSS_INR": "5000",
        "WING_WIDTH_STEPS": "2",
        "TARGET_PROFIT_PCT": "50.0",
        "PRODUCT_TYPE": "NRML",
        "MAX_HOLD_DAYS": "5",
    })
    assert cfg.MAX_LOSS_INR == 5000.0
    assert cfg.WING_WIDTH_STEPS == 2
    assert cfg.TARGET_PROFIT_PCT == 50.0
    assert cfg.PRODUCT_TYPE == "NRML"
    assert cfg.MAX_HOLD_DAYS == 5


def test_override_via_env():
    cfg = _reload_config({"MAX_LOSS_INR": "7500"})
    assert cfg.MAX_LOSS_INR == 7500.0

import pytest

from kaub.analyse import analyser
from kaub.config import charger_config
from kaub.situation import situation_hors_ligne


@pytest.fixture(scope="session")
def cfg():
    return charger_config()


@pytest.fixture(scope="session")
def situation(cfg):
    return situation_hors_ligne(cfg)


@pytest.fixture(scope="session")
def analyse(cfg, situation):
    return analyser(cfg, situation)

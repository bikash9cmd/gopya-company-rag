from pathlib import Path

import pytest

from gopya.answer import ExtractiveAnswerer
from gopya.config import settings
from gopya.corpus import load
from gopya.index import Index
from gopya.pipeline import Gopya
from gopya.rbac import Directory
from gopya.trace import TraceLog


@pytest.fixture(scope="session")
def cfg():
    return settings()


@pytest.fixture(scope="session")
def chunks(cfg):
    return load(cfg.docs_dir)


@pytest.fixture(scope="session")
def index(chunks, tmp_path_factory):
    return Index.build(chunks, Path(tmp_path_factory.mktemp("idx")))


@pytest.fixture(scope="session")
def directory(cfg):
    return Directory(cfg.roles_file, cfg.users_file)


@pytest.fixture()
def gopya(index, directory, cfg):
    return Gopya(index, directory, cfg, answerer=ExtractiveAnswerer(cfg.min_coverage), traces=TraceLog(None))

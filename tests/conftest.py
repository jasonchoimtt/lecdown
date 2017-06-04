import tempfile
import os
import os.path
import shutil
import pytest

from lecdown import config


@pytest.fixture(scope='function')
def integration_env(monkeypatch):
    cwd = os.getcwd()
    tmpdir = os.path.join(cwd, 'tmp')
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # We use a tmp directory in the repo instead of /tmp, since tmpfs on
        # Linux does not support extended file attributes
        with tempfile.TemporaryDirectory(dir=tmpdir) as name:
            os.chdir(name)
            try:
                monkeypatch.setattr(config, 'LOCAL_CONFIG_FILE', os.path.join(name, 'lecdown.json'))
                monkeypatch.setattr(
                    config, 'GLOBAL_CONFIG_FILE', os.path.join(name, 'lecdown-global.json'))
                config.config.clear()
                config.config.update(config.get_default_global_config())
                config.config.update(config.get_default_local_config())
                yield
            finally:
                os.chdir(cwd)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

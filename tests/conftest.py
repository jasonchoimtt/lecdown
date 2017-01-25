import tempfile
import os
import os.path
import pytest

from lecdown import config


@pytest.fixture(scope='function')
def integration_env(monkeypatch):
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as name:
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

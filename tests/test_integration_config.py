import os.path

from lecdown import config
from lecdown.main import main


def test_init(integration_env):
    main(['init'])
    assert os.path.exists(config.LOCAL_CONFIG_FILE)


def test_init_global(integration_env):
    main(['init', '--global'])
    assert os.path.exists(config.GLOBAL_CONFIG_FILE)


def test_config_invariance(integration_env):
    global_obj = config.get_default_global_config()
    global_obj['depth'] = 3
    global_obj['cookies'] = [42]
    config.config_write(config.GLOBAL_CONFIG_FILE, global_obj)
    with open(config.GLOBAL_CONFIG_FILE) as f:
        global_str = f.read()

    local_obj = config.get_default_local_config()
    local_obj['depth'] = 5
    local_obj['sources'] = ['heart of gold']
    config.config_write(config.LOCAL_CONFIG_FILE, local_obj)
    with open(config.LOCAL_CONFIG_FILE) as f:
        local_str = f.read()

    with config.open_config():
        pass

    with open(config.GLOBAL_CONFIG_FILE) as f:
        assert f.read() == global_str

    with open(config.LOCAL_CONFIG_FILE) as f:
        assert f.read() == local_str

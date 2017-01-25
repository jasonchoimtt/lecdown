from collections import OrderedDict
from contextlib import contextmanager
import json
import os.path
import time


class Strategy:
    AUTO = 'auto'
    SYNC = 'sync'
    IGNORE = 'ignore'
    ONCE = 'once'


class Status:
    NONE = 'none'  # Default
    UPDATED = 'updated'
    UP_TO_DATE = 'up to date'
    SKIPPED = 'skipped'
    NOT_FOUND = 'not found'
    ERROR = 'error'



class Record:
    def __init__(self, **kwargs):
        self.last_status = Status.NONE
        # Time when this url was first discovered
        self.discovered_at = time.time()
        # Time when the resource was last downloaded
        self.updated_at = None

        # Filename provided by the server
        self.filename = None
        self.content_type = None
        self.scraper_attrs = None
        self.sha = None

        self.local_path = None
        self.local_modified = False

        self.strategy = Strategy.AUTO

        if kwargs:
            self.__dict__.update(kwargs)


def config_read(path):
    with open(path) as f:
        obj = json.load(f, object_pairs_hook=OrderedDict)
    if 'records' in obj:
        for k, v in obj['records'].items():
            obj['records'][k] = Record(**v)
    return obj


def config_write(path, obj, mode='w'):
    if 'records' in obj:
        records = {}
        for k, v in obj['records'].items():
            records[k] = v.__dict__
        obj = dict(obj)
        obj['records'] = records
    with open(path, mode) as f:
        json.dump(obj, f, indent=4)


def create_config():
    if not os.path.exists(GLOBAL_CONFIG_FILE):
        config_write(GLOBAL_CONFIG_FILE, get_default_global_config(), mode='x')
        print('Wrote {}'.format(GLOBAL_CONFIG_FILE))
    config_write(LOCAL_CONFIG_FILE, get_default_local_config(), mode='x')
    print('Wrote {}'.format(LOCAL_CONFIG_FILE))


@contextmanager
def open_config():
    config.clear()
    try:
        global_obj = config_read(GLOBAL_CONFIG_FILE)
    except FileNotFoundError:
        global_obj = get_base_config()
        config.update(global_obj)
    else:
        config.update(global_obj)

    local_obj = config_read(LOCAL_CONFIG_FILE)
    for key, value in local_obj.items():
        if key in MERGEABLE_KEYS:
            config[key].extend(value)
        else:
            config[key] = value

    yield

    for key in WRITABLE_LOCAL_KEYS:
        local_obj[key] = config[key]
    config_write(LOCAL_CONFIG_FILE, local_obj)

    for key in WRITABLE_GLOBAL_KEYS:
        global_obj[key] = config[key]
    config_write(GLOBAL_CONFIG_FILE, global_obj)


def get_base_config():
    return OrderedDict([
        ('renamers', []),
        ('depth', 0),
        ('cookies', {})
        ])


def get_default_global_config():
    return OrderedDict([
        ('renamers', []),
        ('depth', 0),
        ('cookies', [])
        ])


def get_default_local_config():
    return OrderedDict([
        ('sources', []),
        ('records', {})
        ])


config = OrderedDict()

GLOBAL_CONFIG_FILE = os.path.join(os.path.expanduser("~"), '.lecdown.json')
LOCAL_CONFIG_FILE = 'lecdown.json'

WRITABLE_GLOBAL_KEYS = ['cookies']
WRITABLE_LOCAL_KEYS = ['sources', 'records']
MERGEABLE_KEYS = ['renamers']

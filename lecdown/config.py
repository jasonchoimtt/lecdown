from collections import defaultdict, OrderedDict
from contextlib import contextmanager
import json
import time
import os


class Strategy:
    AUTO = 'auto'
    SYNC = 'sync'
    IGNORE = 'ignore'
    ONCE = 'once'


class Record:
    def __init__(self, content=None):
        self.last_status = 0
        # Time when this link was first found
        self.discovered_at = time.time()
        # Time when the resource was first retrieved
        self.found_at = None
        # Time when the resource was last downloaded
        self.updated_at = None
        self.checked_at = None

        self.content_type = None
        self.etag = None
        self.sha= None
        self.local_path = None

        self.strategy = Strategy.AUTO

        if content:
            self.__dict__.update(content)


def to_defaultdict(typ, obj):
    out = defaultdict(typ)
    for k, v in obj.items():
        out[k] = typ(v)
    return out


def from_defaultdict(dct):
    out = {}
    for k, v in dct.items():
        out[k] = dict(v.__dict__)
    return out


def create_config():
    with open(CONFIG_FILE, 'x') as f:
        json.dump(config, f, indent=4)


@contextmanager
def open_config():
    with open(CONFIG_FILE) as f:
        obj = json.load(f, object_pairs_hook=OrderedDict)

    config.clear()
    config.update(obj)
    config['records'] = to_defaultdict(Record, config['records'])

    yield

    obj = OrderedDict(config)
    obj['records'] = from_defaultdict(obj['records'])
    with open(CONFIG_FILE, 'w') as f:
        json.dump(obj, f, indent=4)


HOME_PATH = os.path.expanduser("~")
CONFIG_FILE = HOME_PATH + '/.lecdown.json'

config = OrderedDict([
    ('sources', []),
    ('records', defaultdict(Record)),
    ('cookies', [])])

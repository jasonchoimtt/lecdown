import argparse
import cgi
from collections import defaultdict, OrderedDict
from contextlib import contextmanager
import datetime
import hashlib
import json
import mimetypes
import os
import os.path
from pprint import pprint
import re
import time
import urllib.parse

import requests
from selenium import webdriver
from tabulate import tabulate


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


CONFIG_FILE = 'lecdown.json'

config = OrderedDict([
    ('sources', []),
    ('records', defaultdict(Record)),
    ('cookies', [])])


def generate_local_path(filename, record):
    if not filename:
        filename = 'download'
    if '.' not in filename:
        filename += mimetypes.guess_extension(record.content_type or '') or ''

    filename = cleanup_filename(filename)

    filename = filename.replace('_', ' ')
    for c in r'[]/\;><&*:%=+@!#^()|?^':
        filename = filename.replace(c, ' ')
    filename = filename.strip()
    filename = re.sub(r' +', ' ', filename)
    filename = filename.replace(' ', '_')

    return filename


@contextmanager
def open_driver():
    driver = webdriver.Chrome()

    try:
        yield driver
    finally:
        driver.quit()


def collect_links(urls):
    with open_driver() as driver:
        links = set()

        for dest_url in urls:
            print('navigating to {}'.format(dest_url))

            parsed = urllib.parse.urlparse(dest_url)
            cookies = [c for c in config['cookies'] if parsed.netloc.endswith(c['domain'])]
            if cookies:
                # Selenium dictates that we have to go to that domain to set a
                # cookie
                driver.get('{0.scheme}://{0.netloc}/favicon.ico'.format(parsed))
                for cookie in cookies:
                    driver.add_cookie(cookie)

            driver.get(dest_url)

            url = driver.current_url.partition('#')[0]

            a_tags = driver.find_elements_by_tag_name('a')
            for a in a_tags:
                link = a.get_attribute('href')
                if not link:
                    continue
                link = link.partition('#')[0]
                # Selenium resolves the link, so it is absolutely absolute
                if link == url or link in urls:  # source page
                    continue
                if not link.startswith('http://') and not link.startswith('https://'):
                    continue
                links.add(link)

    return links


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


def process_link(link):
    record = config['records'][link]
    if record.strategy == Strategy.IGNORE:
        return 0, 0

    # We ignore cache-control policy, and only use the ETag header to
    # validate with server.
    headers = {}
    if record.etag and os.path.exists(record.local_path):
        headers['If-None-Match'] = record.etag
        # If the file is missing, we should redownload that
    resp = requests.get(link, headers=headers)

    if not resp.ok:
        # Record status and skip
        record.last_status = resp.status_code
        if record.last_status != 404:
            print('{0.last_status} ({0.strategy}) {0.content_type} {1}'.format(record, link))
        return 0, 1
    else:
        record.content_type = resp.headers.get('Content-Type')
        record.etag = resp.headers.get('ETag')
        record.last_status = resp.status_code

        record.checked_at = time.time()

        if record.strategy == Strategy.AUTO:
            strategy = auto_strategy(link, record)
            record.strategy = strategy

        print('{0.last_status} ({0.strategy}) {0.content_type} {1}'.format(record, link))

        if record.strategy == Strategy.IGNORE:  # AUTO -> IGNORE
            return 0, 1
        if resp.status_code == 304:  # Not Modified
            return 0, 1

        if not record.local_path:
            filename = None
            if 'Content-Disposition' in resp.headers:
                _, params = resp.headers.get('Content-Disposition')
                if 'filename' in params:
                    filename = params['filename']

            if not filename:
                path = urllib.parse.urlparse(resp.url).path
                filename = os.path.basename(path)
                filename = urllib.parse.unquote(filename)

            record.local_path = generate_local_path(filename, record)

        target = record.local_path
        if os.path.exists(target):
            base, dot, ext = target.rpartition('.')
            target = base + '_updated' + dot + ext

        with open(target + '.download', 'xb') as f:
            hasher = hashlib.sha1()
            for block in resp.iter_content(1024):
                f.write(block)
                hasher.update(block)
            record.sha = hasher.hexdigest()

        os.rename(target + '.download', target)
        print('-> {}'.format(target))
        record.updated_at = time.time()
        if not record.found_at:
            record.found_at = record.found_at

        if record.strategy == Strategy.ONCE:
            record.strategy = Strategy.IGNORE

        return 1, 1


def auto_strategy(link, record):
    if record.content_type.startswith('text/html'):
        return Strategy.IGNORE
    else:
        return Strategy.SYNC


def cleanup_filename(filename):
    filename = re.sub(r'(?i)\b(lecture|lec|l)\s?\b', '', filename)
    filename = re.sub(r'(?i)\b(tutorial|tut|t)\s?\b', 'T', filename)
    filename = re.sub(r'(?i)\b(assignment|assgn|asgn|assg|ass)\s?\b', 'HW', filename)
    filename = filename.replace('-', '')
    if filename.endswith('.pdf'):
        filename = filename[0].upper() + filename[1:]
    return filename


def main_download():
    links = collect_links(config['sources'])

    updated = 0
    checked = 0

    for link in links:
        try:
            u, c = process_link(link)
            updated += u
            checked += c
        except Exception:
            raise

    print('updated {}, checked {}'.format(updated, checked))


parser = argparse.ArgumentParser(description='Download lecture materials.')
parser.set_defaults(mode='download')
subparsers = parser.add_subparsers(title='subcommands')

def create_mode(mode, *args, **kwargs):
    parser = subparsers.add_parser(mode, *args, **kwargs)
    parser.set_defaults(mode=mode)
    return parser

create_mode('init', help='Create config file')

parser_add_source = create_mode('add-source', help='Add source page')
parser_add_source.add_argument('source')

create_mode('browser', help='Show interactive browser')

parser_ls = create_mode('ls', help='List downloaded files')
parser_ls.add_argument('--all', '-a', action='store_true', help='List not downloaded files as well')

parser_mv = create_mode('mv', help='Rename file')
parser_mv.add_argument('source')
parser_mv.add_argument('target')

create_mode('download', help='Download lecture materials')


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


def main():
    args = parser.parse_args()

    if args.mode == 'init':
        with open(CONFIG_FILE, 'x') as f:
            json.dump(config, f, indent=4)

    elif args.mode == 'add-source':
        with open_config():
            source = args.source
            scheme = urllib.parse.urlparse(source).scheme
            if scheme == '':
                source = 'http://' + source
            elif scheme not in ['http', 'https']:
                print('Unsupported scheme: {}'.format(scheme))
            config['sources'].append(source)

    elif args.mode == 'browser':
        with open_config():
            with open_driver() as driver:
                try:
                    while True:
                        print('[S]ave cookie / [Q]uit > ', end='')
                        l = input().lower()
                        if l == 'q':
                            break
                        elif l == 's':
                            cookies = driver.get_cookies()
                            print('saved {} cookies.'.format(len(cookies)))
                            config['cookies'].extend(cookies)
                except KeyboardInterrupt:
                    pass

    elif args.mode == 'ls':
        with open_config():
            files = []
            afiles = []
            for link, record in config['records'].items():
                if record.local_path:  # Downloaded
                    filename = record.local_path
                    timestamp = datetime.datetime.fromtimestamp(record.updated_at) \
                        .strftime('%b %d %H:%M')
                    strategy = record.strategy.upper()

                    try:
                        stat = os.stat(record.local_path)
                    except FileNotFoundError:
                        timestamp += '?'
                    else:
                        # Check if the file has changed, using mtime then sha1sum
                        if stat.st_mtime > record.updated_at:
                            hasher = hashlib.sha1()
                            with open(record.local_path, 'rb') as f:
                                hasher = hashlib.sha1()
                                for block in iter(lambda: f.read(4096), b''):
                                    hasher.update(block)
                            sha = hasher.hexdigest()

                            if sha != record.sha:
                                timestamp += '*'

                    files.append((filename, timestamp, strategy, link))
                elif args.all and record.checked_at:  # checked_at: File actually existed
                    content_type = '[{}]'.format(record.content_type.partition(';')[0])
                    timestamp = datetime.datetime.fromtimestamp(record.checked_at) \
                        .strftime('%b %d %H:%M')
                    strategy = record.strategy.upper()

                    afiles.append((content_type, timestamp, strategy, link))
            files.sort()
            files.extend(afiles)

            print(tabulate(files, tablefmt='plain'))

    elif args.mode == 'mv':
        with open_config():
            records = [r for r in config['records'].values() if r.local_path == args.source]
            assert len(records) == 1, 'Found more than 1 records for the file'
            record = records[0]
            os.rename(args.source, args.target)
            record.local_path = args.target

    else:
        with open_config():
            main_download()


if __name__ == '__main__':
    main()

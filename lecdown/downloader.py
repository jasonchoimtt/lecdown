import cgi
import hashlib
from itertools import count
import mimetypes
import os.path
import re
import time
import urllib.parse

import requests

from .config import Strategy, config


def auto_strategy(link, record):
    if record.content_type.startswith('text/html'):
        return Strategy.IGNORE
    else:
        return Strategy.SYNC


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


def cleanup_filename(filename):
    filename = re.sub(r'(?i)\b(lecture|lec|l)\s?\b', '', filename)
    filename = re.sub(r'(?i)\b(tutorial|tut|t)\s?\b', 'T', filename)
    filename = re.sub(r'(?i)\b(assignment|assgn|asgn|assg|ass)\s?\b', 'HW', filename)
    filename = filename.replace('-', '')
    if filename.endswith('.pdf'):
        filename = filename[0].upper() + filename[1:]
    return filename


def file_digest(fname):
    hasher = hashlib.sha1()
    with open(fname, 'rb') as f:
        hasher = hashlib.sha1()
        for block in iter(lambda: f.read(4096), b''):
            hasher.update(block)
    return hasher.hexdigest()


def download_file(link, verbose=False, dest_dir=''):
    records = config['records']
    record = records[link]
    if record.strategy == Strategy.IGNORE:
        return 0, 0

    def show_record():
        print('{:<4}{:<8}{:<20}{}'.format(
            record.last_status or '',
            record.strategy.upper(),
            record.content_type or '',
            urllib.parse.unquote(link)))

    # We ignore cache-control policy, and only use the ETag header to
    # validate with server.
    headers = {}
    if record.etag and os.path.exists(record.local_path):
        headers['If-None-Match'] = record.etag
        # If the file is missing, we should redownload that
    # cafile = '/usr/local/etc/openssl/cert.pem'
    # cafile = 'cacert.pem'
    # resp = requests.get(link, headers=headers, verify=cafile)
    try:
        resp = requests.get(link, headers=headers)
    except Exception as e:
        print("Exception: ", e, "link: ", link)
        return 0, 1

    if not resp.ok:
        # Record status and skip
        record.last_status = resp.status_code
        if record.last_status != 404:
            show_record()
        return 0, 1
    else:
        record.content_type = resp.headers.get('Content-Type') or record.content_type
        record.etag = resp.headers.get('ETag')
        record.last_status = resp.status_code

        record.checked_at = time.time()

        if record.strategy == Strategy.AUTO:
            strategy = auto_strategy(link, record)
            record.strategy = strategy

        if resp.status_code != 304 or verbose:
            show_record()

        if record.strategy == Strategy.IGNORE:  # AUTO -> IGNORE
            return 0, 1
        if resp.status_code == 304:  # Not Modified
            return 0, 1

        if not record.local_path:
            filename = None
            if 'Content-Disposition' in resp.headers:
                _, params = cgi.parse_header(resp.headers.get('Content-Disposition'))
                if 'filename' in params:
                    filename = params['filename']

            if not filename:
                path = urllib.parse.urlparse(resp.url).path
                filename = os.path.basename(path)
                filename = urllib.parse.unquote(filename)

            # Generate a unique target filename for this URL
            target = generate_local_path(filename, record)
            if any(r.local_path == target for r in records.values() if r != record):
                base, dot, ext = target.rpartition('.')
                for serial in count(0):
                    target = base + '.conflict.{}'.format(serial) + dot + ext
                    if not any(r.local_path == target for r in records.values() if r != record):
                        break

            record.local_path = target
        else:
            target = record.local_path

        # Generate a unique temporary filename
        for serial in count(0):
            download = target + ('.{}.download'.format(serial) if serial > 0 else '.download')
            if not os.path.exists(download):
                break

        with open(download, 'xb') as f:
            hasher = hashlib.sha1()
            for block in resp.iter_content(1024):
                f.write(block)
                hasher.update(block)
            record.sha = hasher.hexdigest()

        if os.path.exists(target):
            sha = file_digest(target)
            if sha != record.sha:
                base, dot, ext = target.rpartition('.')
                target = base + '_updated' + dot + ext

        dest_filename = (dest_dir + '/' + target) if dest_dir != '' else target
        os.rename(download, dest_filename)
        print(' -> {}'.format(target))
        record.updated_at = time.time()
        if not record.found_at:
            record.found_at = record.found_at

        if record.strategy == Strategy.ONCE:
            record.strategy = Strategy.IGNORE

        return 1, 1


def check_file(link):
    exists, changed = True, False

    record = config['records'][link]
    try:
        stat = os.stat(record.local_path)
    except FileNotFoundError:
        exists = False
    else:
        # Check if the file has changed, using mtime then sha1sum
        if stat.st_mtime > record.updated_at:
            sha = file_digest(record.local_path)
            if sha != record.sha:
                changed = True

    return exists, changed

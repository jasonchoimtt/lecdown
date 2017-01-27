import importlib
import hashlib
import mimetypes
import os.path
import re
import textwrap
import time
import traceback
import urllib.parse
from xattr import xattr

from .config import Record, Status, Strategy, config


# We use this extended file attribute to indicate the URL of a file
XATTR_KEY_URL = 'user.lecdown.url'


def select_strategy(filename, content_type, **kwargs):
    if content_type and content_type.startswith('text/html'):
        return Strategy.IGNORE
    else:
        return Strategy.SYNC


def select_filename(filename, content_type):
    if '.' not in filename:
        filename += mimetypes.guess_extension(content_type or '') or ''
    return filename


def cleanup_filename(filename):
    filename = re.sub(r'(?i)\b(lecture|lec|l)\s?\b', '', filename)
    filename = re.sub(r'(?i)\b(tutorial|tut|t)\s?\b', 'T', filename)
    filename = re.sub(r'(?i)\b(assignment|assgn|asgn|assg|ass)\s?\b', 'HW', filename)
    filename = filename.replace('-', '')
    if filename.endswith('.pdf'):
        filename = filename[0].upper() + filename[1:]
    return filename


def sanitize_filename(filename):
    # Remove special characters
    for c in r'[]/\;><&*:%=+@!#^()|?^':
        filename = filename.replace(c, ' ')
    # Remove leading and trailing spaces
    filename = filename.strip()
    # Remove multi-spaces
    filename = re.sub(r' +', ' ', filename)
    if filename == 'lecdown.json':
        return 'downloaded-lecdown.json'
    return filename


def file_digest(fname):
    hasher = hashlib.sha1()
    with open(fname, 'rb') as f:
        hasher = hashlib.sha1()
        for block in iter(lambda: f.read(4096), b''):
            hasher.update(block)
    return hasher.hexdigest()


def generate_filename(hint):
    basename, dot, ext = sanitize_filename(hint).partition('.')
    filename = hint
    serial = 0
    while os.path.exists(filename):
        filename = basename + '.{}'.format(serial) + dot + ext
        serial += 1
    return filename


def download_one(scraper, resource, record):
    """
    Download a single file for the given info.

    This function decides the filename of the download and whether to replace a
    given file. It relies on `local_modified` being correctly set by `check_all`
    to process files correctly.
    """
    if record.strategy == Strategy.IGNORE:
        return Status.SKIPPED, None

    url_basename = urllib.parse.unquote(resource['url'].rstrip('/').rpartition('/')[2])
    basename = record.local_path or url_basename or 'untitled'
    save_to = generate_filename(basename + '.download')

    result = {
        'status': Status.ERROR,
        'description': None,
        'filename': None,
        'content_type': None,
        'scraper_attrs': record.scraper_attrs
        }
    try:
        result.update(scraper.download_file(resource, save_to, record.scraper_attrs))
    except Exception:
        result.update({
            'description': traceback.format_exc(),
            'filename': None,
            })

    # Update metadata if there is no error
    if result['status'] != Status.ERROR:
        record.filename = result['filename'] or record.filename or url_basename
        record.content_type = result['content_type'] or record.content_type

    if record.strategy == Strategy.AUTO:
        # Select a strategy if we don't have one already
        record.strategy = select_strategy(
            filename=result['filename'], content_type=result['content_type'], **resource)

        if record.strategy == Strategy.IGNORE and result['status'] == Status.UPDATED:
            # We don't need the file, so let's clean up
            os.unlink(save_to)
            return Status.SKIPPED, None

    record.last_status = result['status']

    description = result['description']

    if result['status'] == Status.UPDATED:
        record.updated_at = time.time()

        record.sha = file_digest(save_to)

        # Handle the downloaded file
        if not record.local_path:
            record.local_path = generate_filename(
                select_filename(result['filename'] or basename, record.content_type))
            os.rename(save_to, record.local_path)
            xattr(record.local_path).set(XATTR_KEY_URL, resource['url'].encode())
        elif not record.local_modified:
            os.unlink(record.local_path)
            os.rename(save_to, record.local_path)
            xattr(record.local_path).set(XATTR_KEY_URL, resource['url'].encode())
        else:
            basename, dot, ext = record.local_path.partition('.')
            updated_local_path = generate_filename(basename + '.updated' + dot + ext)
            os.rename(save_to, updated_local_path)
            description = 'Saved updated version to {}'.format(updated_local_path)

        if record.strategy == Strategy.ONCE:
            record.strategy = Strategy.IGNORE

    record.scraper_attrs = result['scraper_attrs']
    return result['status'], description


def download_with_scraper(scraper_name, sources, verbose=False):
    records = config['records']
    module, _, class_name = scraper_name.rpartition('.')
    Scraper = getattr(importlib.import_module(module), class_name)
    scraper = Scraper()

    resources = scraper.collect_resources(sources, cookies=config['cookies'])

    results = []

    for resource in resources:
        record = records.get(resource['url'])
        if not record:
            record = records[resource['url']] = Record()
        orig_strategy = record.strategy

        status, description = download_one(scraper, resource, record)
        results.append((status, description))

        if verbose or description or status in (Status.UPDATED, Status.ERROR) \
                or orig_strategy == Strategy.AUTO:
            tags = ''
            if orig_strategy == Strategy.AUTO and status == Status.UPDATED:
                tags += ' [NEW]'
            elif orig_strategy == Strategy.AUTO and status == Status.SKIPPED:
                tags += ' [NEW, IGNORED]'
            filename = record.local_path or '[{}]'.format(record.filename or 'file')
            filename += tags
            print('{:<40}{:<12}{:<20}{}'.format(
                filename,
                status.upper(),
                (record.content_type or '').partition(';')[0],
                urllib.parse.unquote(resource['url'])))
            if description:
                print(textwrap.indent(description, '    '))
                print()

    return results



def download_all(verbose=False):
    """
    Classify sources by scrapers and invoke them.
    """
    scrapers = {}
    for source in config['sources']:
        scrapers.setdefault(source['scraper'], []).append(source)

    results = []
    for scraper_name, subsources in scrapers.items():
        results.extend(download_with_scraper(scraper_name, subsources, verbose=verbose))

    return results


def check_all():
    """
    Detect modifications, movements and deletions of tracked files. This updates
    the corresponding records in the config file.
    """
    records = config['records']
    missing = set()

    def get_xattr_url(local_path, default=None):
        try:
            url = xattr(local_path).get(XATTR_KEY_URL).decode()
        except OSError:
            return default
        else:
            return url

    def walk_within_depth():
        for root, dirs, files in os.walk('.'):
            # Each `root` string begins with ./
            if root.count(os.path.sep) > config['depth']:
                del dirs[:]
            for f in files:
                yield os.path.join(root[2:], f)

    def do_move(url, local_path):
        changes.append((url, records[url].local_path, local_path))
        records[url].local_path = local_path
        if not local_path:
            records[url].strategy = Strategy.IGNORE
        missing.remove(url)

    def check_modified(record, stat):
        # Check if the file has changed, using mtime then sha1sum
        record.local_modified = False
        if stat.st_mtime > record.updated_at:
            sha = file_digest(record.local_path)
            if sha != record.sha:
                record.local_modified = True

    # Check all files in our records if
    # 1. They disappeared (deleted or moved somewhere else)
    # 2. They were replaced by other tracked files (using xattrs)
    checked = set()
    updated = {}
    for url, record in records.items():
        if not record.local_path:
            continue
        checked.add(record.local_path)
        try:
            stat = os.stat(record.local_path)
        except FileNotFoundError:
            missing.add(url)
            continue

        x_url = get_xattr_url(record.local_path, url)
        if x_url != url:
            missing.add(url)
            updated[x_url] = record.local_path
        else:
            check_modified(record, stat)

    changes = []

    # Detect replacement of tracked files by tracked files
    for url, local_path in updated.items():
        if url in missing:
            do_move(url, local_path)

    # Detect movement of tracked files
    if missing:
        for local_path in walk_within_depth():
            if local_path in checked:
                continue

            url = get_xattr_url(local_path)
            if url and url in missing:
                do_move(url, local_path)

                if not missing:
                    break

    # Detect deletion of tracked files
    while missing:
        do_move(next(iter(missing)), None)

    # Detect modification of changed tracked files
    for url, _, local_path in changes:
        if local_path:
            stat = os.stat(local_path)
            check_modified(records[url], stat)

    return changes

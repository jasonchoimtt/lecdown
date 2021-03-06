import argparse
from collections import OrderedDict
import datetime
import json
import os
import os.path
import urllib.parse

from tabulate import tabulate
from xattr import xattr

from .browser import open_driver
from .config import Record, Status, Strategy, config, config_write, create_config, \
    get_default_local_config, open_config
from .scrapers import DEFAULT_SCRAPER
from .downloader import download_all, check_all, XATTR_KEY_URL


parser = argparse.ArgumentParser(description='Download lecture materials.')
subparsers = parser.add_subparsers(dest='mode', title='subcommands')


#######################################################################
# init
#######################################################################
parser_init = subparsers.add_parser('init', help='Create config file')

def main_init(args):
    create_config()


#######################################################################
# add-source
#######################################################################
parser_add_source = subparsers.add_parser('add-source', help='Add source page')
parser_add_source.add_argument('source')
parser_add_source.add_argument('--scraper')

def main_add_source(args):
    with open_config():
        source = args.source
        scheme = urllib.parse.urlparse(source).scheme
        if scheme == '':
            source = 'http://' + source
        scraper = args.scraper or DEFAULT_SCRAPER
        config['sources'].append({
            'source': source,
            'scraper': scraper
            })

#######################################################################
# browser
#######################################################################
subparsers.add_parser('browser', help='Show interactive browser')

def main_browser(args):
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

#######################################################################
# ls
#######################################################################
parser_ls = subparsers.add_parser('ls', help='List downloaded files')
parser_ls.add_argument('--all', '-a', action='store_true', help='List not downloaded files as well')

def do_check_all():
    table = [(old, '->', new or 'DELETED', url) for url, old, new in check_all()]
    if table:
        print(tabulate(table, tablefmt='plain'))


def strftime(timestamp):
    if timestamp:
        return datetime.datetime.fromtimestamp(timestamp).strftime('%b %d %H:%M')
    else:
        return ''


def main_ls(args):
    with open_config():
        do_check_all()
        files = []
        afiles = []
        for link, record in config['records'].items():
            if record.local_path:  # Downloaded
                filename = record.local_path
                timestamp = (
                    strftime(record.updated_at) +
                    ('*' if record.local_modified else ''))
                strategy = record.strategy.upper()

                files.append((filename, timestamp, strategy, link))
            elif args.all and record.strategy != Strategy.AUTO:  # AUTO: file actually existed
                content_type = '[{}]'.format((record.content_type or '?').partition(';')[0])
                timestamp = strftime(record.updated_at)
                strategy = record.strategy.upper()

                afiles.append(
                    (-(record.updated_at or 0), (content_type, timestamp, strategy, link)))

        files.sort()
        afiles.sort()
        afiles = [f[1] for f in afiles]
        files.extend(afiles)

        print(tabulate(files, ['File', 'Updated at', 'Strategy', 'URL'], tablefmt='simple'))


#######################################################################
# mv
#######################################################################
parser_mv = subparsers.add_parser('mv', help='Rename file')
parser_mv.add_argument('source')
parser_mv.add_argument('target')

def main_mv(args):
    with open_config():
        records = [r for r in config['records'].values() if r.local_path == args.source]
        assert len(records) == 1, 'Found more than 1 records for the file'
        record = records[0]
        os.rename(args.source, args.target)
        record.local_path = args.target


#######################################################################
# rm
#######################################################################
parser_rm = subparsers.add_parser('rm', help='Remove file')
parser_rm.add_argument('--cached', action='store_true')
parser_rm.add_argument('target')

def main_rm(args):
    with open_config():
        records = [r for r in config['records'].values() if r.local_path == args.target]
        assert len(records) == 1, 'Found more than 1 records for the file'
        record = records[0]
        if not args.cached:
            os.unlink(args.target)
        record.strategy = Strategy.IGNORE
        record.local_path = None


#######################################################################
# download
#######################################################################
parser_download = subparsers.add_parser('download', help='Download lecture materials')
parser_download.add_argument('--verbose', '-v', action='store_true')
parser.set_defaults(verbose=False)

def main_download(args):
    with open_config():
        do_check_all()

        KEYS = [Status.UPDATED, Status.UP_TO_DATE, Status.SKIPPED, Status.NOT_FOUND, Status.ERROR]
        count = {k: 0 for k in KEYS}

        results = download_all()
        for status, _ in results:
            count[status] += 1

        print(', '.join('{} {}'.format(count[k], k) for k in KEYS))


#######################################################################
# download
#######################################################################
parser_migrate = subparsers.add_parser('migrate')

def main_migrate(args):
    with open('lecdown.json') as f:
        old = json.load(f, object_pairs_hook=OrderedDict)

    new_config = get_default_local_config()

    for source in old['sources']:
        new_config['sources'].append({'source': source, 'scraper': DEFAULT_SCRAPER})

    for url, record in old['records'].items():
        last_status = Status.SKIPPED
        if record['last_status'] == 404:
            last_status = Status.NOT_FOUND
        elif record['last_status'] == 304 and record['updated_at']:
            last_status = Status.UP_TO_DATE
        elif record['last_status'] == 200 and record['updated_at']:
            last_status = Status.UPDATED
        new_config['records'][url] = Record(
            last_status=last_status,
            discovered_at=record['discovered_at'],
            updated_at=record['updated_at'],
            filename=urllib.parse.unquote(url.rstrip('/').rpartition('/')[2]),
            content_type=record['content_type'],
            scraper_attrs={'etag': record['etag']},
            sha=record['sha'],
            local_path=record['local_path'],
            local_modified=False,
            strategy=record['strategy'])

        if record['local_path'] and os.path.exists(record['local_path']):
            xattr(record['local_path']).set(XATTR_KEY_URL, url.encode())
            print('Wrote metadata for {}'.format(record['local_path']))

    config_write('lecdown.new.json', new_config)
    print()
    print('Wrote lecdown.new.json')
    print('Check the new config file and replace lecdown.json with it. '
          'Make sure to do a backup!')


def main(args=None):
    args = parser.parse_args(args=args)
    if not args.mode:
        args.mode = 'download'
    # Magical dispatching
    globals()['main_' + args.mode.replace('-', '_')](args)


if __name__ == '__main__':
    main()

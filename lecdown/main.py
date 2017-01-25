import argparse
import datetime
import os
import os.path
import urllib.parse

from tabulate import tabulate

from .browser import open_driver
from .config import Status, Strategy, config, create_config, open_config
from .scrapers import DEFAULT_SCRAPER
from .downloader import download_all, check_all


parser = argparse.ArgumentParser(description='Download lecture materials.')
parser.set_defaults(mode='download')
subparsers = parser.add_subparsers(title='subcommands')

def create_mode(mode, *args, **kwargs):
    parser = subparsers.add_parser(mode, *args, **kwargs)
    parser.set_defaults(mode=mode)
    return parser


#######################################################################
# init
#######################################################################
parser_init = create_mode('init', help='Create config file')

def main_init(args):
    create_config()


#######################################################################
# add-source
#######################################################################
parser_add_source = create_mode('add-source', help='Add source page')
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
create_mode('browser', help='Show interactive browser')

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
parser_ls = create_mode('ls', help='List downloaded files')
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
parser_mv = create_mode('mv', help='Rename file')
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
parser_rm = create_mode('rm', help='Remove file')
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
parser_download = create_mode('download', help='Download lecture materials')
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


def main(args=None):
    args = parser.parse_args(args=args)
    # Magical dispatching
    globals()['main_' + args.mode.replace('-', '_')](args)


if __name__ == '__main__':
    main()

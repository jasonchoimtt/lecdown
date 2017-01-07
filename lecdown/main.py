import argparse
import datetime
import os
import os.path
import urllib.parse

from tabulate import tabulate

from .browser import open_driver, collect_links
from .config import Strategy, config, create_config, open_config
from .downloader import download_file, check_file


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
create_mode('init', help='Create config file')

def main_init(args):
    create_config()


#######################################################################
# add-source
#######################################################################
parser_add_source = create_mode('add-source', help='Add source page')
parser_add_source.add_argument('source')

def main_add_source(args):
    with open_config():
        source = args.source
        scheme = urllib.parse.urlparse(source).scheme
        if scheme == '':
            source = 'http://' + source
        elif scheme not in ['http', 'https']:
            print('Unsupported scheme: {}'.format(scheme))
        config['sources'].append(source)

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

def main_ls(args):
    with open_config():
        files = []
        afiles = []
        for link, record in config['records'].items():
            if record.local_path:  # Downloaded
                filename = record.local_path
                timestamp = datetime.datetime.fromtimestamp(record.updated_at) \
                    .strftime('%b %d %H:%M')
                strategy = record.strategy.upper()

                exists, changed = check_file(link)
                if not exists:
                    timestamp += '?'
                elif changed:
                    timestamp += '*'

                files.append((filename, timestamp, strategy, link))
            elif args.all and record.checked_at:  # checked_at: File actually existed
                content_type = '[{}]'.format(record.content_type.partition(';')[0])
                timestamp = datetime.datetime.fromtimestamp(record.checked_at) \
                    .strftime('%b %d %H:%M')
                strategy = record.strategy.upper()

                afiles.append((-record.checked_at, (content_type, timestamp, strategy, link)))

        files.sort()
        afiles.sort()
        afiles = [f[1] for f in afiles]
        files.extend(afiles)

        print(tabulate(files, tablefmt='plain'))


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
create_mode('download', help='Download lecture materials')

def main_download(args):
    with open_config():
        links = collect_links(config['sources'])

        updated, checked = 0, 0
        for link in links:
            try:
                u, c = download_file(link)
                updated += u
                checked += c
            except Exception:
                raise

        print('updated {}, checked {}'.format(updated, checked))


def main():
    args = parser.parse_args()
    # Magical dispatching
    globals()['main_' + args.mode.replace('-', '_')](args)


if __name__ == '__main__':
    main()

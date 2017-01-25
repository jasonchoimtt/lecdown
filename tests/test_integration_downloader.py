import time
import hashlib
import pytest
from xattr import xattr

from lecdown.config import LOCAL_CONFIG_FILE, Record, Status, Strategy, config, config_write, \
    get_default_local_config, open_config
from lecdown.downloader import download_all, check_all,  XATTR_KEY_URL
from lecdown.scrapers import BaseScraper


def digest(s):
    hasher = hashlib.sha1()
    hasher.update(s.encode())
    return hasher.hexdigest()


class MockScraper(BaseScraper):
    urls = []
    downloads = {}
    sources_collected = set()
    files_downloaded = {}

    def collect_resources(self, sources, cookies):
        MockScraper.sources_collected.update(s['source'] for s in sources)
        print(id(MockScraper))
        return [{'url': u, 'res-attr': 42} for u in self.urls]

    def download_file(self, resource, save_to, scraper_attrs=None, force=False):
        url = resource['url']
        MockScraper.files_downloaded[url] = save_to
        entry = self.downloads[url]
        if 'contents' in entry:
            with open(save_to, 'w') as f:
                f.write(entry['contents'])
        return self.downloads[url]


def setup(urls=[], downloads={}, records={}):
    local_obj = get_default_local_config()
    local_obj['sources'] = [
        {
            'source': 'http://source',
            'scraper': 'test_integration_downloader.MockScraper'
            }
        ]
    local_obj['records'].update(records)
    config_write(LOCAL_CONFIG_FILE, local_obj)

    MockScraper.urls.clear(); MockScraper.urls.extend(urls)
    MockScraper.downloads.clear(); MockScraper.downloads.update(downloads)
    MockScraper.sources_collected.clear()
    MockScraper.files_downloaded.clear()


def test_download_new_file(integration_env):
    setup(
        urls=['http://new_file'],
        downloads={'http://new_file': {'status': Status.UPDATED, 'contents': 'new_file'}})

    with open_config():
        results = download_all()
        assert results == [(Status.UPDATED, None)]

    assert MockScraper.sources_collected == {'http://source'}
    assert 'http://new_file' in MockScraper.files_downloaded

    with open_config():
        assert config['records']['http://new_file'].local_path == 'new_file'

    with open('new_file') as f:
        assert f.read() == 'new_file'


@pytest.mark.parametrize('changed', [True, False])
def test_update_file_hash(integration_env, changed):
    updated_at = time.time()-10
    with open('file', 'w') as f:
        f.write('changed' if changed else 'original')
    setup(
        urls=['http://file'],
        downloads={'http://file': {'status': Status.UPDATED, 'contents': 'updated'}},
        records={
            'http://file': Record(
                last_status=Status.UPDATED, updated_at=updated_at,
                sha=digest('original'),
                local_path='file', local_modified=changed, strategy=Strategy.SYNC)
            }
        )

    with open_config():
        results = download_all()
        assert results == \
            [(Status.UPDATED, 'Saved updated version to file.updated' if changed else None)]

    with open_config():
        record = config['records']['http://file']

        assert record.updated_at > updated_at
        assert record.sha == digest('updated')

        if changed:
            with open('file') as f:
                assert f.read() == 'changed'
            with open('file.updated') as f:
                assert f.read() == 'updated'
        else:
            with open('file') as f:
                assert f.read() == 'updated'


def test_check_deleted_file(integration_env):
    record = Record(
        last_status=Status.UPDATED, updated_at=time.time()-10,
        sha=digest('original'),
        local_path='file', strategy=Strategy.SYNC)
    config['records'].update({'http://file': record})

    changes = check_all()
    assert changes == [('http://file', 'file', None)]
    assert record.local_path == None
    assert record.strategy == Strategy.IGNORE


def test_check_moved_file(integration_env):
    record = Record(
        last_status=Status.UPDATED, updated_at=time.time()-10,
        sha=digest('original'),
        local_path='file', strategy=Strategy.SYNC)
    config['records'].update({'http://file': record})

    with open('file2', 'w') as f:
        f.write('original')
    xattr('file2').set(XATTR_KEY_URL, 'http://file'.encode())

    changes = check_all()
    assert changes == [('http://file', 'file', 'file2')]
    assert record.local_path == 'file2'
    assert record.local_modified == False
    assert record.strategy == Strategy.SYNC


@pytest.mark.parametrize('with_move', [True, False])
def test_check_modified_file(integration_env, with_move):
    record = Record(
        last_status=Status.UPDATED, updated_at=time.time()-10,
        sha=digest('original'),
        local_path='file', strategy=Strategy.SYNC)
    config['records'].update({'http://file': record})

    loc = 'file2' if with_move else 'file'
    with open(loc, 'w') as f:
        f.write('changed')
    xattr(loc).set(XATTR_KEY_URL, 'http://file'.encode())

    check_all()

    assert record.local_modified == True


def test_check_replaced_and_modified_file(integration_env):
    record = Record(
        last_status=Status.UPDATED, updated_at=time.time()-10,
        sha=digest('original'),
        local_path='file', strategy=Strategy.SYNC)
    record2 = Record(
        last_status=Status.UPDATED, updated_at=time.time()-10,
        sha=digest('original2'),
        local_path='file2', strategy=Strategy.SYNC)
    config['records'].update({'http://file': record, 'http://file2': record2})

    # Replace file with file2

    with open('file', 'w') as f:
        f.write('changed')
    xattr('file').set(XATTR_KEY_URL, 'http://file2'.encode())

    changes = check_all()
    assert set(changes) == {('http://file', 'file', None), ('http://file2', 'file2', 'file')}

    assert record.local_path == None
    assert record.strategy == Strategy.IGNORE

    assert record2.local_path == 'file'
    assert record2.strategy == Strategy.SYNC
    assert record2.local_modified == True

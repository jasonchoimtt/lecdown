from abc import ABCMeta
import cgi
import os.path
import urllib.parse
import requests
import traceback

from .config import Status
from .browser import open_driver


DEFAULT_SCRAPER = 'lecdown.scrapers.SeleniumScraper'


class BaseScraper(metaclass=ABCMeta):
    """
    Implement this class and specify the "scraper" option in a source to create
    custom behaviours on collecting and downloading links.
    """
    def collect_resources(self, sources, cookies):
        """
        Collect resource links from the given sources.

        Returns:
            A list of dicts of the shape
            {'url': 'http://path/to/file',
             <other attributes to be used by this scraper>}
        """

    def download_file(self, resource, save_to, scraper_attrs=None, force=False):
        """
        Downloads the file for the given resource, if it is thought to be
        updated. The file should be saved to `save_to`.

        Returns:
            {'status': Status.{UPDATED | UP_TO_DATE | SKIPPED | ERROR | NOT_FOUND},
             'description' <readable details on status> | None,
             'filename': <filename on the server> | None,
             'content_type': <content type> | None,
             'scraper_attrs': <scraper-specific attributes saved to record> | None}
        """


class SeleniumScraper:
    def collect_resources(self, sources, cookies):
        with open_driver() as driver:
            urls = [s['source'] for s in sources]
            links = set()

            for dest_url in urls:
                print('navigating to {}'.format(dest_url))

                parsed = urllib.parse.urlparse(dest_url)
                cookies = [c for c in cookies if parsed.netloc.endswith(c['domain'])]
                if cookies:
                    # Selenium dictates that we go to that domain to set cookie
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

        return [{'url': link} for link in links]

    def download_file(self, resource, save_to, scraper_attrs=None, force=False):
        scraper_attrs = scraper_attrs or {'etag': None}
        headers = {}
        # We ignore cache-control policy, and only use the ETag header to
        # validate with server.
        if scraper_attrs.get('etag') and not force:
            headers['If-None-Match'] = scraper_attrs['etag']
        resp = requests.get(resource['url'], headers=headers)

        if not resp.ok:
            if resp.status_code == 404:
                return {
                    'status': Status.NOT_FOUND
                    }
            else:
                return {
                    'status': Status.ERROR,
                    'description': 'HTTP Error {}'.format(resp.status_code)
                    }
        else:
            # Detect filename from Content-Disposition
            filename = None
            if 'Content-Disposition' in resp.headers:
                _, params = cgi.parse_header(resp.headers.get('Content-Disposition'))
                if 'filename' in params:
                    filename = params['filename']

            if not filename:
                # This is important when the request redirected us
                path = urllib.parse.urlparse(resp.url).path.rstrip('/')
                filename = os.path.basename(path)
                filename = urllib.parse.unquote(filename) or None

            if resp.status_code != 304:
                with open(save_to, 'xb') as f:
                    f.write(resp.content)

            scraper_attrs = dict(scraper_attrs)
            scraper_attrs['etag'] = resp.headers.get('ETag')

            return {
                'status': Status.UPDATED if resp.status_code != 304 else Status.UP_TO_DATE,
                'filename': filename,
                'content_type': resp.headers.get('Content-Type'),
                'scraper_attrs': scraper_attrs
                }

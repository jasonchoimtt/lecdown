from contextlib import contextmanager
import urllib.parse

from config import config
from selenium import webdriver


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

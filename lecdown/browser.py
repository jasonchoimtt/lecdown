from contextlib import contextmanager

from selenium import webdriver


@contextmanager
def open_driver():
    driver = webdriver.Chrome()

    try:
        yield driver
    finally:
        driver.quit()

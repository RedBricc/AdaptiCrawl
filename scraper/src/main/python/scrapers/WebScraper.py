import logging
import time

import regex
from selenium import webdriver
from services import SettingsService

SettingsService = SettingsService.service


def get_driver(url, loading_delay, timeout):
    options = webdriver.ChromeOptions()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--incognito')

    if SettingsService.get_webscraper_setting('headless'):
        options.add_argument('--headless')

    driver = try_start_driver(options, url, loading_delay, timeout)
    driver.set_window_size(1920, 1080)

    time.sleep(loading_delay)

    return driver


def try_start_driver(options, url, loading_delay, timeout):
    for _ in range(timeout):
        try:
            driver = webdriver.Chrome(options)
            driver.get(url)
            return driver
        except:
            time.sleep(loading_delay)
            logging.log(19, f"Failed to start driver for {url}, retrying...")
    raise Exception(f"Failed to start driver for {url} after {timeout} attempts")


def get_page(url, loading_delay, timeout):
    tag_count_cutoff = SettingsService.get_webscraper_setting('tag_count_cutoff')
    retry_count = SettingsService.get_webscraper_setting('retry_count')
    retry_interval = SettingsService.get_webscraper_setting('retry_interval')

    driver = get_driver(url, loading_delay, timeout)
    page_source, tag_count = None, 0

    for _ in range(retry_count):
        page_source = driver.page_source
        tag_count = count_tags(page_source)

        if tag_count > tag_count_cutoff:
            break

        logging.warning(f"Page source for {url} has only {tag_count} tags, retrying after {retry_interval} seconds...")
        time.sleep(retry_interval)
    logging.info(f"Found {tag_count} tags for {url}")

    return driver


def count_tags(page_source):
    tag_regex = regex.compile('<[^\\/>]+>')
    tag_count = len(tag_regex.findall(page_source))

    return tag_count

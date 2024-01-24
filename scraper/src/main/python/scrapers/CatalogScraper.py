import logging
import time
import timeit

from datetime import datetime
from pathlib import Path

from scrapers import WebScraper
from element_finder.PaginationHandler import HandlerType
from services import SettingsService
from preprocessing import ValueTagger, HtmlCleaner
from element_finder import BlockFinder, PaginationHandler

SettingsService = SettingsService.service


def scrape(domain, locale, url, configuration=None):
    logging.info(f"Scraping {domain} ({locale})")

    loading_delay = SettingsService.get_catalog_setting('loading_delay')
    timeout = SettingsService.get_catalog_setting('timeout')
    max_page_count = SettingsService.get_catalog_setting('max_page_count')
    retry_timeout = SettingsService.get_catalog_setting('retry_timeout')
    min_record_count = SettingsService.get_catalog_setting('min_record_count')

    start = timeit.default_timer()
    driver = WebScraper.get_page(url, loading_delay, timeout)
    logging.info(f"Web Scraper: {timeit.default_timer() - start}")

    records = {}
    current_page = 1
    use_fallback, has_retried = False, False

    interaction_buttons, ignored_cleaning_steps = None, []
    if configuration is not None:
        interaction_buttons = configuration.get('interaction_buttons')
        ignored_cleaning_steps = configuration.get('ignored_cleaning_steps') or []

    handler = None
    while current_page < max_page_count + 1:
        page_source = driver.page_source

        clean_soup = clean_data(page_source, url, ignored_cleaning_steps)
        tagged_soup = tag_values(clean_soup)
        blocks = find_blocks(tagged_soup, use_fallback)

        if current_page == 1 and len(blocks) <= 6:
            use_fallback = True
            blocks = find_blocks(tagged_soup, use_fallback)

        if len(blocks) <= 6:
            if has_retried is False:
                logging.info(f"Found less than 6 blocks on page {current_page}")
                result = PaginationHandler.try_interaction_buttons(driver, interaction_buttons)

                if result is False:
                    logging.info(f"Retrying in {retry_timeout} seconds...")
                    time.sleep(retry_timeout)
                    has_retried = True

                continue
        else:
            has_retried = False

        for block in blocks:
            alias = block['alias']
            records[alias] = block

        handler, output_page = PaginationHandler.next_page(driver, page_source, blocks, current_page, handler, interaction_buttons)

        logging.info(f"Found {len(blocks)} blocks on page {current_page}")

        if current_page > 1 and handler in [HandlerType.LIST, HandlerType.INFINITE_SCROLL]:
            current_page = output_page
            break

        current_page = output_page + 1

    logging.info(f"Final size: {len(records)} records\nFound {current_page} pages")

    if len(records) < min_record_count:
        logging.error(f"Found less than {min_record_count} records!")

        take_screenshot(domain, locale, driver)

        return []

    driver.quit()
    records = unpack_records(records)

    return records


def clean_data(page_source, url, ignored_cleaning_steps):
    start = timeit.default_timer()
    soup = HtmlCleaner.clean_data(page_source, url, ignored_cleaning_steps)
    logging.info(f"Html Cleaner: {timeit.default_timer() - start}")

    return soup


def tag_values(soup):
    start = timeit.default_timer()
    soup = ValueTagger.tag_values(soup)
    logging.info(f"Value Tagger: {timeit.default_timer() - start}")

    return soup


def find_blocks(soup, use_fallback):
    start = timeit.default_timer()
    blocks = BlockFinder.find_blocks(soup, fallback=use_fallback)
    logging.info(f"Block Finder [fallback={use_fallback}]: {timeit.default_timer() - start}")

    return blocks


def unpack_records(records):
    unpacked = []
    for alias, record in records.items():
        unpacked_record = {}

        for key, value in record.items():
            if key not in ['tag', 'index', 'group_id', 'parent']:
                unpacked_record[key] = value

        unpacked.append(unpacked_record)

    return unpacked


def take_screenshot(domain, locale, driver):
    folder_path = Path(__file__).parent.joinpath('../../../../../screenshots').resolve()
    path_string = str(folder_path).replace('\\', '/')
    file_path = f"{path_string}/{domain}_{locale.replace(':', '_')}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"

    result = driver.save_screenshot(file_path)

    if result is False:
        logging.error("Could not save screenshot!")


if __name__ == '__main__':
    logging.getLogger().handlers = []
    logging.basicConfig(level=18)
    sites = [
        ("test", "lv", "https://www.1a.lv/c/datoru-komponentes-tikla-produkti/komponentes/procesori/2vr", None),
    ]

    for site_domain, site_locale, site_url, site_configuration in sites:
        site_timer = timeit.default_timer()
        site_records = scrape(site_domain, site_locale, site_url, site_configuration)
        logging.info(f"Total time: {timeit.default_timer() - site_timer}")
        logging.log(18, site_records)

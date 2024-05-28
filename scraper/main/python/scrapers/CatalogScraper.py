import logging
import time
import timeit
from copy import copy

from datetime import datetime
from multiprocessing import Event

from element_finder.PaginationHandler import HandlerType

from scrapers import WebScraper
from scrapers.ScraperSettings import ScraperSettings, ScraperType, StopException
from scrapers.WebScraper import save_tree
from services import SettingsService, ImageService, LoggingService
from preprocessing import ValueTagger, HtmlCleaner
from element_finder import BlockFinder, PaginationHandler

settings_service = SettingsService.service


class InsufficientRecordsException(Exception):
    pass


def scrape(scraper_settings: ScraperSettings, run_timeout_event, process_timeout):
    start = timeit.default_timer()

    logging.info(f"Scraping {scraper_settings.domain}({scraper_settings.locale}) "
                 f"{scraper_settings.url} with proxy: {scraper_settings.proxy}")

    min_record_count = settings_service.get_catalog_setting('min_record_count')
    record_count_warning = settings_service.get_catalog_setting('record_count_warning')
    max_page_count = settings_service.get_catalog_setting('max_page_count')
    retry_timeout = settings_service.get_catalog_setting('retry_timeout')

    records = {}
    current_page, last_page = 1, 1
    last_blocks = []
    has_retried = False
    failed_handlers = []
    pagination_handler = None

    records_with_images = ImageService.get_records_with_images(scraper_settings)
    default_images = ImageService.get_default_images()

    locale_configuration = scraper_settings.configuration
    if locale_configuration is not None and locale_configuration.preferred_pagination_handler is not None:
        pagination_handler = HandlerType[locale_configuration.preferred_pagination_handler.upper()]

    driver = WebScraper.open_page(scraper_settings)
    try:
        while current_page < max_page_count + 1:
            soup = WebScraper.get_indexed_soup(driver, scraper_settings)

            cleaned_soup = clean_data(soup, scraper_settings)
            tagged_soup = tag_values(cleaned_soup, scraper_settings)

            check_timeout(run_timeout_event, start, process_timeout)

            new_blocks = find_blocks(tagged_soup, driver, scraper_settings, records_with_images, default_images, records)

            if len(new_blocks) < min_record_count:
                # Wait for the page to load and press interaction buttons
                if has_retried is False:
                    logging.info(f"Found too few ({len(new_blocks)}) new blocks on page {current_page}")
                    result = PaginationHandler.try_interaction_buttons(driver, locale_configuration.interaction_buttons)

                    if result is False:
                        logging.info(f"Retrying in {retry_timeout} seconds...")
                        has_retried = True
                        time.sleep(retry_timeout)
                    elif result is True:
                        has_retried = True
                        current_page -= 1

                    continue
            else:
                has_retried = False

            if last_page == 1 and len(new_blocks) == 0 and pagination_handler is not None:
                logging.info(f"No new blocks found, trying different pagination handler...")

                failed_handlers.append(pagination_handler)
                pagination_handler = None
                current_page = 1

            if len(new_blocks) > 0:
                logging.info(f"Found {len(new_blocks)} new blocks on page {current_page}")
                for block in new_blocks:
                    alias = block['alias']
                    records[alias] = block
                last_blocks = new_blocks

            check_timeout(run_timeout_event, start, process_timeout)

            pagination_handler = PaginationHandler.next_page(
                driver, soup, last_blocks, current_page, pagination_handler,
                locale_configuration.interaction_buttons, failed_handlers, scraper_settings)

            if pagination_handler is None and current_page > 1:
                break

            last_page = current_page
            current_page += 1

            check_timeout(run_timeout_event, start, process_timeout)

        logging.info(f"Final size: {len(records)} records. Found {current_page} pages")

        if len(records) < record_count_warning or settings_service.is_stage():
            logging.warning(f"Saving screenshot for {scraper_settings.domain}({scraper_settings.locale})")

            ImageService.save_screenshot(driver, scraper_settings)

        WebScraper.close_page(driver)

        if len(records) < min_record_count and scraper_settings.configuration.ignore_min_record_count is False:
            raise InsufficientRecordsException(f"Too few records ({len(records)})!")

        records = clean_records(records)
    except SystemExit or KeyboardInterrupt:
        exit(-1)

    return records


def clean_data(soup, scraper_settings):
    start = timeit.default_timer()
    soup = HtmlCleaner.clean_data(soup, scraper_settings)
    logging.info(f"Html Cleaner: {timeit.default_timer() - start:.3f}s")

    if scraper_settings.save_trees is True:
        save_tree('cleaned.html', soup)

    return soup


def tag_values(soup, scraper_settings):
    start = timeit.default_timer()
    soup = ValueTagger.tag_values(copy(soup), scraper_settings)
    logging.info(f"Value Tagger: {timeit.default_timer() - start:.3f}s")

    if scraper_settings.save_trees is True:
        save_tree('tagged.html', soup)

    return soup


def find_blocks(soup, driver, scraper_settings, records_with_images, default_images, records):
    start = timeit.default_timer()
    blocks = BlockFinder.find_new_blocks(soup, driver, scraper_settings, records_with_images, default_images, records)
    logging.info(f"Block Finder: {timeit.default_timer() - start:.3f}s")

    return blocks


def get_new_block_count(blocks, records):
    new_block_count = 0

    for block in blocks:
        alias = block['alias']
        if alias not in records:
            new_block_count += 1

    return new_block_count


def clean_records(records):
    unpacked = []
    for alias, record in records.items():
        unpacked_record = {}

        for key, value in record.items():
            if key not in ['tag', 'index', 'group_id', 'parent']:
                unpacked_record[key] = value

        unpacked.append(unpacked_record)

    return unpacked


def check_timeout(run_timeout_event, process_timeout, start):
    if run_timeout_event.is_set():
        raise StopException("Run timeout event set, stopping scraping")
    elif timeit.default_timer() - start > process_timeout:
        raise StopException("Process timeout reached, stopping scraping")


# Used in manual testing
if __name__ == '__main__':
    LoggingService.setup_logger(datetime.now(), 18)

    sites = [
        # Testing
         ("ss", "nl", "https://www.ottodegooijer.nl/occasions/", {
             "ignore_min_record_count": True,
             "ignored_cleaning_steps": ["remove_excluded_tags"]
         }),
        # Sites with proxy
        ("autoplius", "make:fiat",
         "https://en.autoplius.lt/ads/used-cars?make_id=86&has_damaged_id=10924&is_condition_new=0", {
             "use_proxy": True
         }),
        # Sites with interaction_buttons
        ("ss", "make:chevrolet", "https://www.ss.com/lv/transport/cars/chevrolet/sell/photo/", {"configuration": {
            "interaction_buttons": [
                "body > div.fc-consent-root > div.fc-dialog-container > div.fc-dialog.fc-choice-dialog > div.fc-footer-buttons-container > div.fc-footer-buttons > button.fc-button.fc-cta-consent.fc-primary-button"
            ]
        }}),
        ("bravoauto", "lt", "https://bravoauto.lt/automobiliai", {
            "interaction_buttons": [
                "#HeaderModal > button"
            ]
        }),
        # Pagination, view more, infinite scroll, list
        ("verteauto", "lv", "https://www.verteauto.lv/lv/mazlietoti-auto-riga", None),
        ("mollerauto", "lv",
         "https://mollerauto.lv/lv_en/used-cars.html?customFilters=country:253&sortKey=name&sortDirection=DESC", None),
        ("autoselect", "lv", "https://autoselect.lv/cars/", None),
        ("faktoauto", "lt", "https://www.naudoti-automobiliai.lt/", None),
    ]

    for site_domain, site_locale, site_url, site_configuration in sites:
        site_timer = timeit.default_timer()

        site_settings = ScraperSettings(
            scraper_type=ScraperType.CATALOG,
            domain=site_domain,
            locale=site_locale,
            url=site_url,
            configuration=site_configuration,
            run_id=0,
            driver=WebScraper.get_driver(),
            save_trees=True
        )

        site_records = scrape(site_settings, Event(), process_timeout=10000)

        logging.info(f"Total time: {timeit.default_timer() - site_timer}")

        pass  # Put breakpoint here to inspect the results

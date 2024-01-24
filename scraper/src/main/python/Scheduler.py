import logging
import os
import sys
import time
import timeit
import traceback
from multiprocessing import Pool

import schedule
from datetime import datetime

from scrapers import CatalogScraper, StaticScraper
from db import Database
from services import SettingsService

SettingsService = SettingsService.service
failed_scrapes = []
startup_timestamp = datetime.now()


def scrape_static_pages():
    domain, locale, url, records, scraping_time, session_id = None, None, None, None, 0, None

    configured_domains = SettingsService.get_static_settings()
    run_id = Database.save_run()
    start = timeit.default_timer()

    try:
        for domain in configured_domains:
            target_urls = SettingsService.get_static_setting(domain, 'urls')

            for target in target_urls.items():
                start = timeit.default_timer()

                locale, url = target
                records = try_scrape_page(StaticScraper, domain, locale, url, run_id)

                if records is None:
                    failed_scrapes.append((domain, locale, url, None, run_id, 1))
                else:
                    logging.info(f"Total time: {timeit.default_timer() - start}\n")
    except:
        log_scrape_error(domain, locale, url, traceback.format_exc(), "static scraping domain", run_id,
                         timeit.default_timer() - start, records, session_id)
        failed_scrapes.append((domain, locale, url, None, run_id, 1))

    Database.end_run(run_id)


def init_catalog_scraping():
    logging.info(f"Starting catalog scraping")

    start = timeit.default_timer()
    url_counter = 0
    run_id = Database.save_run()

    target_domains = SettingsService.get_catalog_setting('target_domains')
    pool_capacity = SettingsService.get_catalog_setting('pool_capacity')
    process_timeout = SettingsService.get_catalog_setting('process_timeout')

    active_scrapes = []

    with Pool(processes=pool_capacity) as pool:
        configuration_dict = {}

        for domain, locales in target_domains.items():
            configuration_dict[domain] = []
            for locale_configuration in locales:
                locale = locale_configuration.get('locale')
                url = locale_configuration.get('url')
                configuration = locale_configuration.get('configuration')

                configuration_dict[domain].append((domain, locale, url, configuration))

        locale_configurations = reorder_locale_configurations(configuration_dict)
        locale_configurations.reverse()

        for domain, locale, url, configuration in locale_configurations:
            process = pool.apply_async(scrape_catalog_page,
                                       args=(domain, locale, url, configuration, run_id, startup_timestamp,))
            active_scrapes.append(process)
            if len(active_scrapes) <= pool_capacity:
                time.sleep(5)

        for process in active_scrapes:
            error = None
            try:
                result = process.get(timeout=process_timeout)
            except TimeoutError:
                logging.error(f"Timeout error occurred: {traceback.format_exc()}")
                error = traceback.format_exc()
                process.terminate()
            except:
                logging.error(f"Error occurred : {traceback.format_exc()}")
                error = traceback.format_exc()

            if error is not None:
                failed_scrapes.append((domain, locale, url, configuration, run_id, 1))
                continue

            domain, locale, url, configuration, error, records = result

            if records is None:
                failed_scrapes.append((domain, locale, url, configuration, run_id, 1))
            else:
                url_counter += 1

    logging.info(f"Successfully scraped {url_counter} urls in {(timeit.default_timer() - start) / 3600} hours!")

    active_scrapes.clear()
    Database.end_run(run_id)


def reorder_locale_configurations(configuration_dict):
    """
    Reorder locale configurations to avoid scraping the same domain too often
    :param configuration_dict: dict of domain: [(domain, locale, url, configuration)]
    :return: reordered list of locale configurations with each domain as spread out as possible
    """
    sorted_configurations = sorted(configuration_dict.items(), key=lambda x: len(x[1]), reverse=True)
    reordered = sorted_configurations.pop(0)[1]

    if len(sorted_configurations) == 0:
        return reordered

    other_configurations = reorder_locale_configurations(dict(sorted_configurations))

    split_value = max(1, int(len(other_configurations) / max(1, len(reordered) - 1)))
    remainder = len(other_configurations) - split_value * (len(reordered) - 1)
    if remainder > 0:
        split_value += 1

    split_count, next_index, records_added = 1, 1, 0

    for index, configuration in enumerate(other_configurations):
        if records_added >= split_value:
            if remainder > 0 and split_count == remainder:
                split_value += -1
            next_index += 1
            split_count += 1
            records_added = 0

        reordered.insert(next_index, configuration)
        records_added += 1
        next_index += 1

    return reordered


def scrape_catalog_page(domain, locale, url, configuration, run_id, timestamp):
    try:
        setup_logger(timestamp)
        records = try_scrape_page(CatalogScraper, domain, locale, url, run_id, configuration)

        if records is None:
            return domain, locale, url, configuration, 'Not enough records found!', None
        return domain, locale, url, configuration, None, records
    except:
        return domain, locale, url, configuration, traceback.format_exc(), None


def retry_failed_scrapes():
    if len(failed_scrapes) == 0:
        logging.info(f"No failed scrapes to retry")
        return

    retry_startup_time_minutes = SettingsService.get_scheduler_setting('retry_startup_time_minutes')
    retry_wait_time_minutes = SettingsService.get_scheduler_setting('retry_wait_time_minutes')
    retry_attempts = SettingsService.get_scheduler_setting('retry_attempts')

    logging.info(f"Retrying {len(failed_scrapes)} failed scrapes after {retry_startup_time_minutes} minutes")
    time.sleep(retry_startup_time_minutes * 60)

    failed_scrapes_copy = failed_scrapes.copy()
    failed_scrapes.clear()

    for domain, locale, url, configuration, run_id, attempts in failed_scrapes_copy:
        if attempts < retry_attempts + 1:
            records = try_scrape_page(CatalogScraper, domain, locale, url, run_id, configuration, error_message='retrying')

            if records is None:
                failed_scrapes.append((domain, locale, url, configuration, run_id, attempts + 1))

        time.sleep(retry_wait_time_minutes * 60)


def try_scrape_page(scraper, domain, locale, url, run_id, configuration=None, error_message='scraping'):
    min_record_count = SettingsService.get_catalog_setting('min_record_count')
    record_count_warning = SettingsService.get_catalog_setting('record_count_warning')
    start = timeit.default_timer()

    logging.info(f"Scraping {domain} {locale} {url}")
    records, session_id, error = None, None, None

    try:
        records = scraper.scrape(domain, locale, url, configuration)

        session_id = Database.save_scrape(domain, locale, url, records, 'Saving records',
                                          timeit.default_timer() - start, run_id)

        if len(records) < min_record_count:
            raise Exception(f"Error: Too few records ({len(records)})!")

        db_start = timeit.default_timer()

        Database.save_records(records, url, session_id, domain)

        if len(records) > record_count_warning:
            Database.update_scrape(session_id, records, 'Success', timeit.default_timer() - start)
        else:
            Database.update_scrape(session_id, records,
                                   f'Warning: Low record count ({len(records)})', timeit.default_timer() - start)
        logging.info(f"Database save time: {timeit.default_timer() - db_start}")

        logging.info(f"Total time: {timeit.default_timer() - start}\n")
    except:
        log_scrape_error(domain, locale, url, traceback.format_exc(), error_message, run_id,
                         timeit.default_timer() - start, records, session_id)
        records = None
    finally:
        return records


def log_scrape_error(domain, locale, url, error, message, run_id, scraping_time, records, session_id):
    logging.error(f"Error {message} {domain} {locale} {url}: {error}")

    if session_id is None:
        Database.save_scrape(domain, locale, url, records,
                             f"Error: {message} traceback: {error}", scraping_time, run_id)
    else:
        Database.update_scrape(session_id, records, f"Error: {message} traceback: {error}", scraping_time)


def setup_logger(timestamp):
    logging.addLevelName(19, "SCRAPER_DEBUG")
    logging.addLevelName(18, "DETAILED")

    time_format = "%Y-%m-%d %H:%M:%S"
    formatted_date = timestamp.strftime('%Y-%m-%d_%H-%M')
    file_string = f"../../../../logs/scheduler_{formatted_date}.log"
    log_format = '%(asctime)s P[%(process)-5d] %(levelname)-11s %(message)s'

    logging.getLogger().handlers = []

    if SettingsService.is_prod():
        logging.basicConfig(filename=file_string, format=log_format, level=logging.INFO, datefmt=time_format)
    elif SettingsService.is_stage():
        logging.basicConfig(filename=file_string, format=log_format, level=19, datefmt=time_format)
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    else:
        logging.basicConfig(filename=file_string, format=log_format, level=19, datefmt=time_format)
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    if __name__ == "__main__":
        logging.info(f"[Running in {SettingsService.get_env()} mode]")


def log_heartbeat():
    logging.info(f"Scheduler waiting for tasks")


if __name__ == "__main__":
    if SettingsService.is_prod():
        schedule.every().day.at("04:00").do(init_catalog_scraping)
    elif SettingsService.is_stage():
        schedule.every().day.at("21:00").do(init_catalog_scraping)

    schedule.every(30).minutes.do(retry_failed_scrapes)
    schedule.every().hour.do(log_heartbeat)

    try:
        os.mkdir("../../../../logs")
        os.mkdir("../../../../screenshots")
    except:
        pass

    setup_logger(startup_timestamp)

    scrape_on_startup = SettingsService.get_scheduler_setting('scrape_on_startup')

    if 8 < datetime.now().hour < 19 and scrape_on_startup or SettingsService.is_dev():
        try:
            init_catalog_scraping()
        except:
            logging.critical(f"Near fatal error occurred: {traceback.format_exc()}")

    logging.info(f"Scheduler started")

    while True:
        try:
            schedule.run_pending()
        except:
            logging.critical(f"Near fatal error occurred: {traceback.format_exc()}")
        finally:
            time.sleep(1)

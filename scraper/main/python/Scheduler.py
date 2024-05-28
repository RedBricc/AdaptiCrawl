import logging
import multiprocessing
import multiprocessing as mp
import os
import signal
import subprocess
import time
import timeit
import traceback

import schedule
from datetime import datetime, timedelta

from scrapers import CatalogScraper, StaticScraper, VdpScraper, WebScraper
from scrapers.ScraperSettings import ScraperSettings, ScraperType, BatchSettings
from services import SettingsService, LoggingService, ProxyService, CatalogService, VdpService

settings_service = SettingsService.service


class SchedulerProps:
    def __init__(self):
        self.startup_timestamp = datetime.now()
        self.scheduler_timeout_events = {}

        for scraper_type in ScraperType:
            self.scheduler_timeout_events[scraper_type.value] = []

    def clear(self):
        for scraper_type, scraper_events in self.scheduler_timeout_events.items():
            for event in scraper_events:
                logging.info(f"Clearing event {event} for {scraper_type}")
                event.set()


failed_scrapes = []
scheduler_props = SchedulerProps()


def scrape_static_pages():
    scraper_settings, session_id = None, None

    configured_domains = settings_service.get_static_settings()
    run_id = CatalogService.save_run(ScraperType.CATALOG)
    start = timeit.default_timer()

    try:
        for domain in configured_domains:
            target_urls = settings_service.get_static_setting(domain, 'urls')

            for target in target_urls.items():
                start = timeit.default_timer()

                locale, url = target
                scraper_settings = ScraperSettings(
                    scraper_type=ScraperType.CATALOG_STATIC,
                    domain=domain,
                    locale=locale,
                    url=url,
                    run_id=run_id
                )

                success = try_scrape_page(StaticScraper, scraper_settings, save_catalog_scrape, 'static scraping')

                if success is False:
                    failed_scrapes.append((scraper_settings, 1, start))
                else:
                    logging.info(f"Total time: {timeit.default_timer() - start:.3f}s\n")
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        log_scrape_error(scraper_settings, traceback.format_exc(), "static scraping domain",
                         timeit.default_timer() - start, None, session_id)

    CatalogService.end_run(run_id)


def try_catalog_scraping():
    """
    Try to scrape the catalog pages.
    The scraping will be divided into separate processes to better use the available resources.
    """
    try:
        init_catalog_scraping()
    except SystemExit or KeyboardInterrupt:
        logging.error(f"Terminating scrape attempt due to System exit")
        exit(-1)
    except:
        logging.critical(f"NEAR FATAL ERROR: {traceback.format_exc()}")


def try_vdp_scraping():
    """
    Try to scrape the VDP pages.
    The scraping will be divided into separate processes to better use the available resources.
    """
    try:
        init_vdp_scraping()
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.critical(f"NEAR FATAL ERROR: {traceback.format_exc()}")


def init_catalog_scraping():
    """
    Divide the catalog scraping into separate processes and scrape each page, saving the results to the database
    """
    start = timeit.default_timer()
    logging.info(f"Starting catalog scraping")

    run_id = CatalogService.save_run(ScraperType.CATALOG)

    target_domains = settings_service.get_target_domains()
    scraper_configurations = get_locale_configurations(target_domains, run_id)

    batch_size = settings_service.get_scheduler_setting('catalog_batch_size', default=1)
    pool_capacity = settings_service.get_scheduler_setting('catalog_pool_capacity', default=8)
    batch_configurations = batch_scraper_configurations(scraper_configurations, batch_size, pool_capacity)

    run_pool(ScraperType.CATALOG, start, batch_configurations, scrape_catalog_page)

    CatalogService.end_run(run_id)


def get_locale_configurations(target_domains, run_id):
    """
    Get a list of locale configurations to scrape.
    :param run_id: The id of the run.
    :param target_domains: Dict of domain: [locale_configuration]
    :return: List of reordered locale configurations
    """
    proxies = ProxyService.get_proxies()

    configuration_dict = {}
    for domain, locales in target_domains.items():
        configuration_dict[domain] = []
        proxy_index = 0
        for locale_configuration in locales:
            locale = locale_configuration.get('locale')
            url = locale_configuration.get('url')
            configuration = locale_configuration.get('configuration')

            scraper_settings = ScraperSettings(
                scraper_type=ScraperType.CATALOG,
                domain=domain,
                locale=locale,
                url=url,
                configuration=configuration,
                run_id=run_id
            )

            if scraper_settings.configuration.use_proxy is True:
                scraper_settings.proxy = proxies[(proxy_index + run_id) % len(proxies)]
                proxy_index += 1

            configuration_dict[domain].append(scraper_settings)

    return reorder_locale_configurations(configuration_dict)


def reorder_locale_configurations(configuration_dict):
    """
    Reorder locale configurations to avoid scraping the same domain too often
    :param configuration_dict: dict of ScrapingSettings
    :return: reordered list of locale configurations with each domain as spread out as possible
    """
    if len(configuration_dict) == 0:
        return []

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
            if 0 < remainder == split_count:
                split_value += -1
            next_index += 1
            split_count += 1
            records_added = 0

        reordered.insert(next_index, configuration)
        records_added += 1
        next_index += 1

    return reordered


def batch_scraper_configurations(scraper_configurations, batch_size, pool_size):
    proxies = ProxyService.get_proxies()

    if len(scraper_configurations) == 0:
        return []

    batch_count = (int(len(scraper_configurations) / batch_size)
                   + (1 if len(scraper_configurations) % batch_size > 0 else 0))

    batch_settings = []
    for i in range(batch_count):
        batch_settings.append(BatchSettings())

    proxy_id = 0
    for p in range(batch_count // pool_size + 1):
        for i, configuration in enumerate(
                scraper_configurations[p * batch_size * pool_size:(p + 1) * batch_size * pool_size]):
            batch_id = min(batch_count - 1, i % pool_size + p * pool_size)
            batch_settings[batch_id].settings.append(configuration)

            # Only assign proxy if the configuration requires it
            if configuration.proxy is not None and batch_settings[batch_id].proxy is None:
                batch_settings[batch_id].proxy = proxies[proxy_id % len(proxies)]
                proxy_id += 1

    logging.info(f"Scraping {len(scraper_configurations)} catalog pages in {len(batch_settings)} batches "
                 f" with pool capacity {pool_size} and batch size {batch_size}")

    return batch_settings


def scrape_catalog_page(scraper_settings: ScraperSettings):
    """
    Scrape a catalog page from a separate process
    :return: ScraperSettings and True if successful, False otherwise.
    """
    process_timeout = settings_service.get_scheduler_setting('catalog_process_timeout_minutes') * 60

    try:
        if session_stop_event.is_set():
            logging.error(
                f"Terminating due to session timeout {scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}")
            return False

        return try_scrape_page(CatalogScraper, scraper_settings, save_catalog_scrape, 'scraping catalog',
                               session_stop_event, process_timeout)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Error occurred during process execution: {traceback.format_exc()}")
        return False


def run_pool(scraper_type, start_timestamp, batch_configurations, scrape_function, retry_failed=True):
    pool_capacity = settings_service.get_scheduler_setting(f'{scraper_type.value}_pool_capacity', default=1)
    timeout = settings_service.get_scheduler_setting(f'{scraper_type.value}_run_timeout_minutes') * 60
    startup_stagger_delay = (settings_service
                             .get_scheduler_setting(f'{scraper_type.value}_startup_stagger_delay', default=1))
    batch_timeout = settings_service.get_scheduler_setting(f'{scraper_type.value}_batch_timeout_minutes') * 60

    run_timeout_event = mp.Event()
    scheduler_props.scheduler_timeout_events[scraper_type.value].append(run_timeout_event)

    active_scrapes = []
    url_counter = 0

    with mp.Pool(processes=pool_capacity, initializer=init_worker, initargs=(run_timeout_event,), maxtasksperchild=1) as pool:
        for batch_settings in batch_configurations:
            if run_timeout_event.is_set():
                logging.warning(f"Terminating run")
                break

            async_result = pool.apply_async(batch_scrape_page,
                                            args=(batch_settings, scrape_function, scheduler_props.startup_timestamp))
            active_scrapes.append((batch_settings, async_result,))

            wait_start = timeit.default_timer()
            if len(active_scrapes) < pool_capacity:
                while wait_start + startup_stagger_delay > timeit.default_timer():
                    pass  # Wait with a busy loop to avoid sleeping the process to avoid pool hanging at exit

        for batch_settings, async_result in active_scrapes:
            if timeit.default_timer() > start_timestamp + timeout:
                logging.warning(f"Run timeout reached, terminating")
                run_timeout_event.set()
                break

            try:
                results = async_result.get(batch_timeout)
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.error(f"Error occurred during process execution: {traceback.format_exc()}")
                results = [False] * len(batch_settings.settings)

            for i, success in enumerate(results):
                if success is True:
                    url_counter += 1
                elif retry_failed is True:
                    failed_scrapes.append((batch_settings.settings[i], 1, start_timestamp))

        scheduler_props.scheduler_timeout_events[scraper_type.value].remove(run_timeout_event)

        pool.terminate()  # Terminate the pool manually to avoid pool hanging at exit
        logging.info(f"Exiting pool for {scraper_type.value} scraper")

    logging.info(
        f"Successfully scraped {url_counter} urls in {(timeit.default_timer() - start_timestamp) / 3600} hours")


def init_vdp_scraping():
    """
    Scrape VDP page for unvisited records and save the results in record_details table.
    """
    start = timeit.default_timer()
    logging.info(f"Starting VDP scraping")

    run_id = CatalogService.save_run(ScraperType.VDP)

    scraper_configurations = get_vdp_configuration_list(run_id)

    vdp_batch_size = settings_service.get_scheduler_setting('vdp_batch_size', default=100)
    vdp_pool_capacity = settings_service.get_scheduler_setting('vdp_pool_capacity', default=12)
    batch_configurations = batch_scraper_configurations(scraper_configurations, vdp_batch_size, vdp_pool_capacity)

    logging.info(
        f"Scraping {len(scraper_configurations)} VDP pages in {len(batch_configurations)} batches on run {run_id}")
    run_pool(ScraperType.VDP, start, batch_configurations, scrape_vdp_page, retry_failed=False)

    CatalogService.end_run(run_id)


def get_vdp_configuration_list(run_id):
    """
    Get a list of configurations to scrape in order of priority.
    In order of priority:
    1. Recently added records.
    2. Backlog records that don't belong to a platform site.
    3. Records that do not have an identity field (VIN, registration number and SDK).
    4. Backlog records that belong to a platform site.
    Each priority subset is reordered to avoid scraping the same domain too often.
    :param run_id: The id of the run.
    :return: List of configurations to scrape.
    """
    priority_targets = VdpService.get_priority_configurations(run_id)
    competitor_backlog_targets = VdpService.get_competitor_backlog_configurations(run_id)
    inconclusive_targets = VdpService.get_inconclusive_configurations(run_id)
    platform_backlog_targets = VdpService.get_platform_backlog_configurations(run_id)

    priority_scraper_configurations = reorder_locale_configurations(priority_targets)
    competitor_backlog_configurations = reorder_locale_configurations(competitor_backlog_targets)
    inconclusive_configurations = reorder_locale_configurations(inconclusive_targets)
    platform_backlog_configurations = reorder_locale_configurations(platform_backlog_targets)

    return (priority_scraper_configurations +
            competitor_backlog_configurations +
            inconclusive_configurations +
            platform_backlog_configurations)


def init_worker(event):
    global session_stop_event
    session_stop_event = event


def batch_scrape_page(batch_settings, scraper_function, timestamp):
    LoggingService.setup_logger(timestamp)

    if session_stop_event.is_set():
        logging.error(f"Terminating batch due to session timeout")
        return [False] * len(batch_settings.settings)

    start = timeit.default_timer()

    logging.info(f"Starting batch scraping")

    success_list = [False] * len(batch_settings.settings)

    driver = None
    try:
        driver = WebScraper.get_driver(batch_settings.proxy)
        for i, scraper_settings in enumerate(batch_settings.settings):
            if session_stop_event.is_set():
                logging.error(f"Terminating batch due to session timeout")
                return success_list
            try:
                try:
                    driver.current_url
                except SystemExit or KeyboardInterrupt:
                    exit(-1)
                except:
                    # The driver might be running, but the tab might have crashed
                    driver.switch_to.window(driver.window_handles[0])
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                if session_stop_event.is_set():
                    logging.error(f"Terminating batch due to session timeout")
                    return success_list
                logging.warning(f"Driver shut down unexpectedly, restarting")
                driver = WebScraper.get_driver(batch_settings.proxy)

            try:
                scraper_settings.proxy = batch_settings.proxy
                scraper_settings.driver = driver

                success = scraper_function(scraper_settings)

                success_list[i] = success
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.error(f"Error occurred during process execution: {traceback.format_exc()}")
    except SystemExit or KeyboardInterrupt:
        session_stop_event.set()
        logging.error(f"Terminating session due to System exit")
        exit(-1)
    finally:
        if driver is not None:
            WebScraper.quit_driver(driver)

        logging.info(f"Batch time: {timeit.default_timer() - start:.3f}s")

        return success_list


def scrape_vdp_page(scraper_settings):
    """
    Scrape a VDP page from a separate process
    :return: ScraperSettings and True if successful, False otherwise.
    """
    process_timeout = settings_service.get_scheduler_setting('vdp_process_timeout_minutes') * 60

    try:
        if session_stop_event.is_set():
            logging.error(
                f"Terminating due to session timeout "
                f"{scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}")
            return False

        return try_scrape_page(VdpScraper, scraper_settings, save_vdp_scrape, 'scraping VDP',
                               session_stop_event, process_timeout)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        return False


def save_vdp_scrape(record, scraper_settings, session_id, scrape_time):
    db_start = timeit.default_timer()

    try:
        VdpService.save_or_update_record(record)

        VdpService.update_scrape(session_id, record, 'Success', scrape_time)

        logging.info(f"Database save time: {timeit.default_timer() - db_start:.3f}s")
        logging.info(f"Total time: {scrape_time}")

        return True
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        log_scrape_error(scraper_settings, traceback.format_exc(), 'saving VDP', scrape_time, record, session_id)
        return False


def get_next_scrape_time():
    try:
        scheduled_catalog_time = (settings_service.get_scheduler_setting('scheduled_catalog_time')
                                  .get(settings_service.get_env()))
        scheduled_vdp_time = (settings_service.get_scheduler_setting('scheduled_vdp_time')
                              .get(settings_service.get_env()))

        next_catalog_time = format_next_time(scheduled_catalog_time)
        next_vdp_time = format_next_time(scheduled_vdp_time)

        if next_vdp_time < next_catalog_time:
            return next_vdp_time
        else:
            return next_catalog_time
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Error occurred while getting next scrape time: {traceback.format_exc()}")

    logging.info(f"No next scrape time found")
    return None


def format_next_time(next_time):
    formatted_time = datetime.strptime(next_time, '%H:%M')
    formatted_time = datetime.now().replace(hour=formatted_time.hour, minute=formatted_time.minute)

    if formatted_time < datetime.now():
        formatted_time += timedelta(days=1)

    return formatted_time


def retry_failed_scrapes():
    if len(failed_scrapes) == 0:
        logging.info(f"No failed scrapes to retry")
        return

    retry_startup_time_minutes = settings_service.get_scheduler_setting('retry_startup_time_minutes')
    max_retry_hours = settings_service.get_scheduler_setting('max_retry_hours')
    next_task_time = get_next_scrape_time()

    retry_wait_time_minutes = settings_service.get_scheduler_setting('retry_wait_time_minutes')
    process_timeout_minutes = settings_service.get_scheduler_setting('retry_process_timeout_minutes', 60)
    logging.info(f"Retrying {len(failed_scrapes)} failed scrapes after {retry_startup_time_minutes} minutes")
    time.sleep(retry_startup_time_minutes * 60)

    failed_scrapes_copy = failed_scrapes.copy()
    failed_scrapes.clear()

    run_timeout_event = mp.Event()
    with mp.Pool(processes=1, initializer=init_worker, initargs=(run_timeout_event,)) as pool:
        for scraper_settings, attempts, time_started in failed_scrapes_copy:
            if time_started + (max_retry_hours * 3600) < timeit.default_timer():
                logging.warning(
                    f"Skipping retry for {scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}"
                    f" because it has become stale after {max_retry_hours} hours")
                continue

            if next_task_time is not None and datetime.now() > next_task_time:
                logging.warning(
                    f"Skipping retry for {scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}"
                    f" due to next task")
                failed_scrapes.append((scraper_settings, attempts, time_started))
                if not run_timeout_event.is_set():
                    run_timeout_event.set()
                continue

            try:
                scraper_settings.proxy = None
                retry_run = pool.apply_async(retry_scrape,
                                             args=(scraper_settings, attempts, scheduler_props.startup_timestamp,
                                                   process_timeout_minutes * 60))

                try:
                    for t in range(process_timeout_minutes):
                        retry_run.wait(60)
                        if retry_run.ready():
                            success = retry_run.get()
                            break
                except SystemExit or KeyboardInterrupt:
                    exit(-1)
                except:
                    logging.error(f"Error occurred during retry process: {traceback.format_exc()}")
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.error(f"Error occurred during retry execution: {traceback.format_exc()}")
                success = False

        if success is False:
            failed_scrapes.append((scraper_settings, attempts + 1, time_started))

        time.sleep(retry_wait_time_minutes * 60)


def retry_scrape(scraper_settings, attempts, startup_timestamp, process_timeout):
    scheduler_props.startup_timestamp = startup_timestamp
    LoggingService.setup_logger(startup_timestamp)

    retry_attempts = settings_service.get_scheduler_setting('retry_attempts')

    success = False
    try:
        if attempts < retry_attempts + 1:
            scraper_settings.proxy = scraper_settings.proxy
            scraper_settings.driver = WebScraper.get_driver(scraper_settings.proxy)

            success = try_scrape_page(CatalogScraper, scraper_settings, save_catalog_scrape, scrape_message='retrying',
                                      process_timeout=process_timeout)

            WebScraper.quit_driver(scraper_settings.driver)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        WebScraper.quit_driver(scraper_settings.driver)

    return success


def try_scrape_page(scraper, scraper_settings, save_function, scrape_message='scraping',
                    run_timeout_event=mp.Event(), process_timeout=180):
    """
    :return: True if successful, False otherwise.
    """

    start = timeit.default_timer()
    records, session_id, error = None, None, None

    try:
        records = scraper.scrape(scraper_settings, run_timeout_event, process_timeout=process_timeout)

        scrape_time = timeit.default_timer() - start
        session_id = CatalogService.save_scrape(scraper_settings, records, 'Saving record data', scrape_time)

        return save_function(records, scraper_settings, session_id, timeit.default_timer() - start)
    except SystemExit or KeyboardInterrupt:
        logging.error(
            f"Terminating due to System exit {scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}")
        exit(-1)
    except:
        log_scrape_error(scraper_settings, traceback.format_exc(), scrape_message,
                         timeit.default_timer() - start, records, session_id)
        return False


def save_catalog_scrape(records, scraper_settings, session_id, scrape_time):
    """
    Save the scraped records to the database.
    :return: True if successful, False otherwise.
    If the found records differ from the average count by more than retry_difference percent,
    the scrape will also be considered unsuccessful and False will be returned.
    """
    db_start = timeit.default_timer()
    success = True

    CatalogService.save_records(records, scraper_settings, session_id)

    retry_difference = settings_service.get_catalog_setting('retry_difference')
    avg_record_count = CatalogService.get_average_count(scraper_settings.url)

    if avg_record_count is not None and abs(avg_record_count - len(records)) > avg_record_count * retry_difference:
        CatalogService.update_scrape(session_id, records,
                                     f'Warning: Suspicious record count {len(records)} (average is {avg_record_count})',
                                     scrape_time)
        success = False
    else:
        CatalogService.update_scrape(session_id, records, 'Success', scrape_time)
    logging.info(f"Database save time: {timeit.default_timer() - db_start:.3f}s")
    logging.info(f"Total time: {scrape_time}\n")

    return success


def log_scrape_error(scraper_settings, error, message, scraping_time, records, session_id):
    logging.error(
        f"Error {message} {scraper_settings.domain} {scraper_settings.locale} {scraper_settings.url}: {error}")

    if session_id is None:
        CatalogService.save_scrape(scraper_settings, records,
                                   f"Error: {message} traceback: {error}", scraping_time)
    else:
        CatalogService.update_scrape(session_id, records, f"Error: {message} traceback: {error}", scraping_time)


def cleanup():
    logging.info(f"Cleanup started")

    if settings_service.is_dev():
        logging.info(f"Skipping cleanup in dev environment")
        return

    logging.info(f"Killing Chrome processes")
    try:
        subprocess.call("TASKKILL /f  /IM  CHROME.EXE")
        subprocess.call("TASKKILL /f  /IM  CHROMEDRIVER.EXE")
    except:
        logging.error(f"Failed to kill Chrome processes:\n{traceback.format_exc()}")
    logging.info(f"Chrome processes killed")

    logging.info(f"Cleaning up old data")
    try:
        # Delete all files in C:\Windows\SystemTemp
        subprocess.call('cd C:\\Windows\\SystemTemp && del /q * && FOR /D %p IN (*) DO rmdir "%p" /s /q', shell=True)
    except:
        logging.error(f"Failed to clean up old data:\n{traceback.format_exc()}")
    logging.info(f"Old data cleaned up")

    logging.info(f"Cleanup done")


def log_heartbeat():
    logging.info(f"Scheduler waiting for tasks")


def try_make_directory(path):
    try:
        os.mkdir(path)
    except FileExistsError:
        pass


def exit_handler(signum, frame):
    try:
        logging.info(f"Scheduler stopped by signal {signal.Signals(signum).name}")
        WebScraper.exit_handler(signum, frame)
        scheduler_props.clear()
    except:
        logging.error(f"Failed to clear scheduler props:\n{traceback.format_exc()}")
    finally:
        exit(-1)


signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)

    scheduled_catalog_time = (settings_service.get_scheduler_setting('scheduled_catalog_time')
                              .get(settings_service.get_env()))
    scheduled_vdp_time = (settings_service.get_scheduler_setting('scheduled_vdp_time')
                          .get(settings_service.get_env()))
    scheduled_cleanup_time = (settings_service.get_scheduler_setting('scheduled_cleanup_time')
                              .get(settings_service.get_env()))

    schedule.every().day.at(scheduled_catalog_time).do(try_catalog_scraping)
    schedule.every().day.at(scheduled_vdp_time).do(try_vdp_scraping)
    if scheduled_cleanup_time is not None:
        schedule.every().day.at(scheduled_cleanup_time).do(cleanup)
    schedule.every().hour.do(retry_failed_scrapes)
    schedule.every(4).hours.do(log_heartbeat)

    try_make_directory("../../../logs")
    try_make_directory("../../../screenshots")
    try_make_directory("../resources")
    try_make_directory("../resources/proxy_extensions")

    LoggingService.setup_logger(scheduler_props.startup_timestamp)

    scrape_catalog_on_startup = settings_service.get_scheduler_setting('scrape_catalog_on_startup')
    scrape_vdp_on_startup = settings_service.get_scheduler_setting('scrape_vdp_on_startup')
    cleanup_on_startup = settings_service.get_scheduler_setting('cleanup_on_startup', default=False)

    if cleanup_on_startup:
        cleanup()

    if scrape_catalog_on_startup or scrape_vdp_on_startup or settings_service.is_dev():
        try:
            if scrape_catalog_on_startup or settings_service.is_dev():
                try_catalog_scraping()
            if scrape_vdp_on_startup or settings_service.is_dev():
                try_vdp_scraping()
        except SystemExit or KeyboardInterrupt:
            logging.error(f"Terminating scheduler due to System exit")
            exit(-1)
        except:
            logging.critical(f"Near fatal error occurred: {traceback.format_exc()}")

    logging.info(f"Scheduler started")

    while True:
        try:
            schedule.run_pending()
        except SystemExit or KeyboardInterrupt:
            logging.error(f"Terminating scheduler due to System exit")
            exit(-1)
        except:
            logging.critical(f"Near fatal error occurred: {traceback.format_exc()}")
        finally:
            time.sleep(1)

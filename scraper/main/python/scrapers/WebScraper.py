import logging
import os
import signal
import time
import timeit
import traceback
from pathlib import Path

import psutil
import regex
from bs4 import BeautifulSoup
from selenium.common import NoSuchWindowException
from selenium.webdriver.common.by import By
from seleniumrequests import Chrome
from undetected_chromedriver import ChromeOptions
from urllib3.exceptions import MaxRetryError

from scrapers import ScraperSettings
from scrapers.ScraperSettings import StopException
from services import SettingsService, ProxyService

settings_service = SettingsService.service
active_drivers = []
processes = {}


def get_driver(proxy=None):
    """
    Initializes a new driver with the specified proxy. Enables Chrome translation.
    """
    start = timeit.default_timer()
    retry_count = settings_service.get_webscraper_setting('retry_count')

    driver = init_driver(retry_count, proxy)

    logging.info(f"WebScraper > Get Driver {timeit.default_timer() - start:.3f}s")

    return driver


def open_page(scraper_settings: ScraperSettings, has_retried=False):
    """
    Attempts to open the page in a new tab.
    """
    start = timeit.default_timer()

    driver = scraper_settings.driver

    try:
        driver.switch_to.new_window('tab')
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except NoSuchWindowException or MaxRetryError:
        driver.switch_to.window(driver.window_handles[0])
        driver.switch_to.new_window('tab')

    try:
        driver.get(scraper_settings.url)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to open page {scraper_settings.url}\n{traceback.format_exc()}")
        raise StopException(f"Failed to open page {scraper_settings.url}")

    logging.info(f"WebScraper > Open Page {timeit.default_timer() - start:.3f}s")

    driver = await_page_load(driver, scraper_settings)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    if is_failed_load(soup):
        if has_retried is True:
            raise StopException(f"Failed to load page: {scraper_settings.url}")
        else:
            logging.warning(f"Failed to load page: {scraper_settings.url}, retrying...")
            close_page(driver)
            return open_page(scraper_settings, has_retried=True)

    logging.info(f"Web Scraper: {timeit.default_timer() - start:.3f}s")

    child_processes = psutil.Process(driver.service.process.pid).children(recursive=True)
    for process in child_processes:
        processes[process.pid] = True

    return driver


def await_page_load(driver: Chrome, scraper_settings: ScraperSettings):
    start = timeit.default_timer()

    retry_count = settings_service.get_webscraper_setting('retry_count')
    retry_interval = settings_service.get_webscraper_setting('retry_interval')
    tag_count_cutoff = settings_service.get_webscraper_setting('tag_count_cutoff')

    tag_count = count_tags(driver, scraper_settings)
    for _ in range(retry_count):
        if tag_count > tag_count_cutoff:
            break

        logging.info(f"Page source for {scraper_settings.url} has only {tag_count} tags, "
                     f"retrying after {retry_interval} seconds...")
        time.sleep(retry_interval)

        tag_count = count_tags(driver, scraper_settings)

    logging.info(f"Found {tag_count} tags for {scraper_settings.url}")

    logging.info(f"WebScraper > Await Page Load {timeit.default_timer() - start:.3f}s")

    return driver


def close_page(driver: Chrome):
    """
    Closes the current tab and switches back to the main tab.
    """
    try:
        logging.info(f"Closing page {driver.current_url} in tab {driver.current_window_handle} "
                     f"PID {driver.service.process.pid}")
        if driver.window_handles[0] != driver.current_window_handle:
            driver.close()
        else:
            logging.warning("Attempted to close the main window")
    except MaxRetryError:
        logging.error(f"Failed to close page\n{traceback.format_exc()}")
    except SystemExit or KeyboardInterrupt:
        logging.error(f"Failed to close page due to termination order \n{traceback.format_exc()}")
        exit(-1)
    finally:
        try:
            driver.switch_to.window(driver.window_handles[0])
        except SystemExit or KeyboardInterrupt:
            logging.error(f"Failed to switch window due to termination order \n{traceback.format_exc()}")
            exit(-1)


def quit_driver(driver):
    """
    Quits the driver and removes it from the active drivers list.
    """
    if driver is None:
        return

    try_quit(driver)
    active_drivers.remove(driver)


def try_quit(driver: Chrome):
    try:
        driver.quit()

        try_reap_orphaned_children(os.getpid())

        for pid in processes.copy():
            try:
                p = psutil.Process(pid)
                p.terminate()

                if p.is_running():
                    p.kill()

                processes.pop(pid)
            except psutil.NoSuchProcess:
                logging.log(18, f"Failed to find process {pid}")
    except SystemExit or KeyboardInterrupt:
        logging.error(f"Failed to quit driver due to termination order\n{traceback.format_exc()}")
        exit(-1)
    except:
        logging.error(f"Failed to quit driver\n{traceback.format_exc()}")


def try_reap_orphaned_children(pid):
    logging.info(f"Reaping orphaned children of process {pid}")

    try:
        current_process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        logging.error(f"Failed to find process {pid}")
        return

    children = current_process.children(recursive=True)
    failed_filicide_attempts = 0
    for child in children:
        if child.pid != os.getpid():
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                failed_filicide_attempts += 1
                logging.log(18, f"Failed to find process {child.pid}")

    if len(children) - failed_filicide_attempts > 0:
        logging.info(f"Terminated {len(children) - failed_filicide_attempts} willing orphaned children")

    unresponsive_children = current_process.children(recursive=True)
    failed_filicide_attempts = 0
    for child in unresponsive_children:
        if child.pid != os.getpid():
            try:
                child.kill()
            except psutil.NoSuchProcess:
                failed_filicide_attempts += 1
                logging.log(18, f"Failed to find process {child.pid}")

    if len(unresponsive_children) - failed_filicide_attempts > 0:
        # Tragic day for the children
        logging.info(f"Killed {len(unresponsive_children) - failed_filicide_attempts} unresponsive orphaned children")


def translate_page(driver, scraper_settings):
    """
    Translates the page to English using Google Translate.
    This is achieved by injecting the Google Translate script directly into the page.
    """
    start = timeit.default_timer()
    translation_delay = settings_service.get_webscraper_setting('translation_delay')

    locale = 'auto'
    if scraper_settings.locale is not None and len(scraper_settings.locale) < 4:
        locale = scraper_settings.locale

    try:
        driver.execute_script("""
            let body = document.getElementsByTagName("body")[0];
            body.innerHTML += '<div id="google_translate_element"></div>';
            
            let translateFunctionScript = document.createElement('script');
            translateFunctionScript.id = 'translateFunctionScript';
            translateFunctionScript.innerHTML = `
                function googleTranslateElementInit() {
                    new google.translate.TranslateElement({
                        pageLanguage: '%s', 
                        includedLanguages: 'en',
                        autoDisplay: false, 
                        multilanguagePage: false
                    }, 'google_translate_element');
                    var a = document.querySelector("#google_translate_element select");
                    a.selectedIndex=0;
                    a.dispatchEvent(new Event('change'));
                }
            `;
            body.appendChild(translateFunctionScript);
            
            let linkScript = document.createElement('script');
            linkScript.src = '//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
            linkScript.id = 'linkScript';
            body.appendChild(linkScript);
        """ % locale)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to inject Google Translate script\n{traceback.format_exc()}")

    for _ in range(50):
        try:
            driver.execute_script("googleTranslateElementInit();")
            time.sleep(translation_delay)

            break
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except:
            if _ == 49:
                logging.info(f"Failed to translate page")
            time.sleep(0.1)

    try:
        driver.execute_script("""
            let cleanupList = [
                document.getElementById('google_translate_element'), 
                document.getElementById('translateFunctionScript'),
                document.getElementById('goog-gt-tt'),
                document.getElementById('linkScript'),
                ...document.getElementsByClassName('skiptranslate')
            ];
            
            for (let i = 0; i < cleanupList.length; i++) {
                if (cleanupList[i] !== null) {
                    try {
                        cleanupList[i].parentNode.removeChild(cleanupList[i]);
                    } catch (e) {}
                }
            }
        """)

        logging.info(f"WebScraper > Translate page {timeit.default_timer() - start:.3f}s")
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to clean up translation elements\n{traceback.format_exc()}")


def is_failed_load(soup):
    failed_load_keys = settings_service.get_webscraper_setting('failed_load_keys')

    for key in failed_load_keys:
        if soup.find(string=regex.compile(f".*{key}.*")) is not None:
            return True

    return False


def init_driver(retry_count, proxy):
    chrome_options = ChromeOptions()
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--lang=en-US')

    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_settings.popups": 0,
        "translate_whitelists": {"et": "en", "lv": "en", "lt": "en", "nl": "en"},
        "translate": {"enabled": "true", "showTranslatedText": "true"},
    }

    chrome_options.add_experimental_option("prefs", prefs)

    # When running in background, the window size is always 1028x648.
    # This is so that local tests are consistent with the production environment.
    chrome_options.add_argument('--window-size=1028,648')

    if settings_service.get_webscraper_setting('headless') is True:
        chrome_options.add_argument('--headless')

    chrome_options = ProxyService.configure_proxy(chrome_options, proxy)
    driver = try_start_driver(chrome_options, retry_count)

    return driver


def try_start_driver(chrome_options, retry_count):
    for _ in range(retry_count):
        driver = None
        try:
            driver = Chrome(options=chrome_options)
            driver.delete_all_cookies()

            active_drivers.append(driver)

            child_processes = psutil.Process(driver.service.process.pid).children(recursive=True)
            for process in child_processes:
                processes[process.pid] = True

            driver.get('chrome://settings/languages')
            apply_chrome_translation_hack()

            return driver
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except:
            quit_driver(driver)
            logging.warning(f"Failed to start driver, retrying...")
    raise Exception(f"Failed to start driver after {retry_count} attempts")


def apply_chrome_translation_hack():
    # Somehow, this is necessary to ensure the next page is translated automatically
    # This is likely due to some bug in the current version of the Chrome driver
    time.sleep(10)

    logging.info("Applied Chrome translation hack")


def count_tags(driver, scraper_settings):
    soup = format_soup(driver, scraper_settings, transform_links=False, translate=False)

    return len(soup.find_all())


def get_indexed_soup(driver, scraper_settings):
    """
    Gets the underlying page data, transforms relative links to absolute ones, and indexes each tag.
    If configured, it also inlines the iframes.
    :return: Indexed soup
    """

    soup = format_soup(driver, scraper_settings, translate=scraper_settings.configuration.translate_page)
    indexed_soup = add_tag_indexes(soup)

    return indexed_soup


def format_soup(driver, scraper_settings, transform_links=True, translate=True):
    start = timeit.default_timer()
    do_inline_iframes = settings_service.get_webscraper_setting('inline_iframes')

    if do_inline_iframes is True:
        soup = inline_iframes(driver, transform_links, start, scraper_settings, translate=translate)
    else:
        if transform_links is True:
            relative_to_absolute_links(driver)
        if translate is True:
            translate_page(driver, scraper_settings)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

    return soup


def inline_iframes(driver, transform_links, start_time, scraper_settings, target_iframe=None, translate=False):
    """
    :return: The soup with the iframe tags replaced by their content.
    """
    iframe_max_duration = settings_service.get_webscraper_setting('iframe_max_duration')

    if target_iframe is not None:
        try:
            driver.switch_to.frame(target_iframe)
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except:
            return ""

    if timeit.default_timer() - start_time > iframe_max_duration:
        return BeautifulSoup(driver.page_source, 'html.parser')

    if transform_links is True:
        relative_to_absolute_links(driver)
    if translate is True:
        translate_page(driver, scraper_settings)

    iframes = try_get_iframes(driver)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    soup_iframes = soup.find_all('iframe')

    for index, iframe in enumerate(iframes):
        if len(soup_iframes) <= index:
            logging.error(f"Failed to find iframe with index {index}")
            break
        frame_source = inline_iframes(driver, transform_links, start_time, scraper_settings, iframe)
        soup_iframe = soup_iframes[index]
        soup_iframe.replace_with(frame_source)

    if target_iframe is not None:
        driver.switch_to.parent_frame()
    else:
        driver.switch_to.default_content()

    return soup


def try_get_iframes(driver):
    try:
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        return iframes
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to get iframes\n{traceback.format_exc()}")
        return []


def relative_to_absolute_links(driver):
    try_replace_relative_links(driver, 'a', 'href')

    upload_record_images = settings_service.get_catalog_setting('upload_record_images')
    hash_record_images = settings_service.get_catalog_setting('hash_record_images')

    if upload_record_images is True or hash_record_images is True:
        try_replace_relative_links(driver, 'img', 'src')


def try_replace_relative_links(driver, tag_name, attribute):
    try:
        driver.execute_script(f"""
            let links = document.getElementsByTagName("{tag_name}");
            for (let i = 0; i < links.length; i++) {{
                try {{
                    links[i].setAttribute("{attribute}", links[i].{attribute});
                }} catch (e) {{}}
            }}
        """)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.debug(f"Failed to replace {attribute} for {tag_name} tag"
                      f"\n{traceback.format_exc()}")


def add_tag_indexes(soup):
    start = timeit.default_timer()

    for index, tag in enumerate(soup.find_all()):
        tag.attrs['scraper-index'] = index

    logging.info(f"WebScraper > Tag Indexer {timeit.default_timer() - start:.3f}s")

    return soup


def quit_all_drivers():
    for driver in active_drivers.copy():
        quit_driver(driver)


def get_file_path(local_path, file_name):
    folder_path = Path(__file__).parent.joinpath(local_path).resolve()
    path_string = str(folder_path).replace('\\', '/')

    return f"{path_string}/{file_name}"


def save_tree(name, soup):
    """
    Save the tag tree to a file
    """

    try:
        file_path = get_file_path('../../debug', name)
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(str(soup.prettify()))
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Could not save tree!{traceback.format_exc()}")
        return


def exit_handler(signum, frame):
    logging.info(f"Exiting drivers by signal {signal.Signals(signum).name}")

    for driver in active_drivers:
        try_quit(driver)

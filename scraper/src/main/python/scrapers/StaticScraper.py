import logging
import time

import regex
from selenium.common import NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By

from scrapers import WebScraper
from services import SettingsService

SettingsService = SettingsService.service


def scrape(domain, locale, url, interaction_buttons=None):
    loading_delay = SettingsService.get_static_setting(domain, 'loading_delay')
    timeout = SettingsService.get_static_setting(domain, 'timeout')

    driver = WebScraper.get_driver(url, loading_delay, timeout)

    accept_cookies(domain, driver, timeout)
    vehicle_container = open_all_pages(domain, driver, timeout)

    vehicle_blocks = get_vehicles(domain, vehicle_container, timeout)
    vehicles = get_attributes(domain, locale, url, vehicle_blocks)

    return vehicles


def accept_cookies(domain, driver, timeout):
    try:
        accept_button_method = SettingsService.get_static_setting(domain, 'accept_button').items()
        accept_button = try_get_element(driver, accept_button_method, timeout)
        accept_button.click()
    except:
        logging.log(19, "No accept button found, continuing...")
        pass


def open_all_pages(domain, driver, timeout):
    scroll_delay = SettingsService.get_static_setting(domain, 'scroll_delay')
    max_pages = SettingsService.get_static_setting(domain, 'max_pages')

    view_more_path = SettingsService.get_static_setting(domain, 'view_more_button').items()

    vehicle_container_path = SettingsService.get_static_setting(domain, 'vehicle_container').items()
    vehicle_container = try_get_element(driver, vehicle_container_path, timeout)
    vehicle_count = get_vehicle_count(domain, vehicle_container, timeout)

    distraction_button_method = SettingsService.get_static_setting(domain, 'distraction_button').items()

    for _ in range(max_pages):
        view_more = scroll_and_click(driver, view_more_path, distraction_button_method, timeout, scroll_delay)
        if view_more is None:
            break
        vehicle_count = wait_for_load(domain, vehicle_container, vehicle_count, timeout)
        logging.info(f"Loaded {vehicle_count} vehicles from {domain}...")

    return vehicle_container


def scroll_and_click(driver, element_path, distraction_path, timeout, scroll_delay):
    element = try_get_element(driver, element_path, timeout)

    for _ in range(timeout):
        try:
            actions = ActionChains(driver)
            actions.scroll_to_element(element).perform()
            time.sleep(scroll_delay)

            scroll_origin = ScrollOrigin.from_element(element)
            actions.scroll_from_origin(scroll_origin, 0, 400).perform()
            time.sleep(scroll_delay)

            element.click()
            return element
        except ElementClickInterceptedException:
            logging.log(19, "Element click intercepted while scrolling, retrying...")
            distraction_button = try_get_element(driver, distraction_path, timeout)
            if distraction_button is not None:
                distraction_button.click()
            time.sleep(1)
        except StaleElementReferenceException:
            logging.log(19, "Element stale while scrolling, retrying...")
            element = try_get_element(driver, element_path, timeout)
        except:
            logging.log(19, "Exception while scrolling, retrying...")
            time.sleep(1)

    return None


def wait_for_load(domain, vehicle_container, old_count, timeout):
    for i in range(timeout):
        vehicle_count = get_vehicle_count(domain, vehicle_container, timeout)
        if vehicle_count > old_count:
            return vehicle_count
        else:
            logging.log(19, f"Vehicle count {vehicle_count} not greater than {old_count}, retrying...")
            time.sleep(1)
    return old_count


def get_vehicle_count(domain, vehicle_container, timeout):
    return len(get_vehicles(domain, vehicle_container, timeout))


def get_vehicles(domain, vehicle_container, timeout):
    vehicle_path = SettingsService.get_static_setting(domain, 'vehicle_path').items()
    return try_get_elements(vehicle_container, vehicle_path, timeout)


def get_attributes(domain, vehicle_location, source, vehicle_blocks):
    attributes = SettingsService.get_static_setting(domain, 'attributes').items()
    vehicle_attributes = []

    for vehicle_block in vehicle_blocks:
        attribute_values = {
            'alias': '',
            'title': None,
            'make': None,
            'model': None,
            'year': 0,
            'mileage': 0,
            'price': '',
            'link': '',
            'competitor_name': domain,
            'location': vehicle_location,
            'source': source
        }

        for attribute in attributes:
            attribute_values[attribute[0]] = get_attribute_value(vehicle_block, attribute)

        if attribute_values['title'] is None:
            attribute_values['title'] = f"{attribute_values['make']} {attribute_values['model']}"
        else:
            make_examples = SettingsService.get_static_setting(domain, 'makes')
            model_regex = SettingsService.get_static_setting(domain, 'model_regex')

            for make_example in make_examples:
                example_regex = regex.compile(regex.escape(make_example), regex.IGNORECASE)
                regex_result = regex.search(example_regex, attribute_values['title'])

                if regex_result is not None:
                    attribute_values['make'] = regex_result.group(0)
                    remaining_title = regex.sub(example_regex, '', attribute_values['title']).strip()
                    model_result = regex.search(model_regex, remaining_title)
                    attribute_values['model'] = model_result.group(0).strip()
                    break

        vehicle_attributes.append(attribute_values)

    return vehicle_attributes


def get_attribute_value(vehicle_block, attribute):
    attribute_element = get_element(vehicle_block, attribute[1].items())
    attribute_type = SettingsService.get_group_setting(attribute[1], 'type')

    try:
        if attribute_type == 'text':
            return get_direct_text(attribute_element)
        elif attribute_type == 'float':
            return get_float(get_direct_text(attribute_element))
        elif attribute_type == 'int':
            return int(get_float(get_direct_text(attribute_element)))
        elif attribute_type == 'href':
            return attribute_element.get_attribute('href')
        elif attribute_type == 'alias':
            link = attribute_element.get_attribute('href')
            alias_regex = SettingsService.get_group_setting(attribute[1], 'regex')
            return regex.search(alias_regex, link).group(0)
        else:
            raise NotImplementedError(f"Attribute type {attribute_type} not implemented!")
    except:
        logging.log(19, f"Failed to get attribute value for {attribute[0]}, returning default...")
        return SettingsService.get_group_setting(attribute[1], 'default')


def get_float(string):
    replaced_trailing_comma = regex.sub(',(?=\\d{2}\\b)', '.', string)
    replaced_delimiter_commas = regex.sub(',(?=\\d{3})', '', replaced_trailing_comma)
    replaced_non_numbers = regex.sub('[^\\d\\.]', '', replaced_delimiter_commas)
    return float(replaced_non_numbers)


def get_direct_text(element):
    children = element.find_elements(By.XPATH, './*')
    if len(children) == 0:
        return element.text
    else:
        rez_text = element.text
        for child in children:
            rez_text = rez_text.replace(child.text, '').strip()
        return rez_text


def try_get_element(driver, method_dict, timeout):
    method, value = unpack_method(method_dict)
    if method is None or value is None:
        logging.log(19, "Method or value is None, returning None...")
        return None

    for _ in range(timeout):
        try:
            return driver.find_element(method, value)
        except NoSuchElementException:
            logging.log(19, f"Element by {method}: {value} not found, retrying...")
            time.sleep(1)
    return None


def try_get_elements(driver, method_dict, timeout):
    method, value = unpack_method(method_dict)
    if method is None or value is None:
        return None

    for _ in range(timeout):
        try:
            return driver.find_elements(method, value)
        except NoSuchElementException:
            logging.log(19, f"Elements by {method}: {value} not found, retrying...")
            time.sleep(1)
        except StaleElementReferenceException:
            logging.log(19, f"Elements by {method}: {value} stale, retrying...")
            time.sleep(1)
    raise TimeoutError(f"Elements by {method}: {value} not found!")


def get_element(driver, method_dict):
    try:
        method, value = unpack_method(method_dict)
        if method is None or value is None:
            return None
        return driver.find_element(method, value)
    except NoSuchElementException:
        logging.log(19, f"Element by {method}: {value} not found, returning None...")
        return None


def unpack_method(method_dict):
    if method_dict is None or len(method_dict) == 0:
        return None, None
    unpacked_method = next(iter(method_dict))
    if unpacked_method[0] == 'xpath':
        method = By.XPATH
    elif unpacked_method[0] == 'id':
        method = By.ID
    elif unpacked_method[0] == 'css_selector':
        method = By.CSS_SELECTOR
    elif unpacked_method[0] == 'class_name':
        method = By.CLASS_NAME
    elif unpacked_method[0] == 'link_text':
        method = By.LINK_TEXT
    elif unpacked_method[0] == 'partial_link_text':
        method = By.PARTIAL_LINK_TEXT
    elif unpacked_method[0] == 'name':
        method = By.NAME
    else:
        raise NotImplementedError(f"Method {unpacked_method[0]} not implemented!")
    value = unpacked_method[1]
    return method, value


if __name__ == "__main__":
    logging.basicConfig(level=19)
    url = 'https://bravoauto.lt/automobiliai'
    vehicles, page_source = scrape('bravoauto', 'lt', url)

    print(vehicles)

    import preprocessing.HtmlCleaner as HtmlCleaner
    with open(f'../../../test/resources/static_raw.html', 'w', encoding='utf-8') as file:
        file.write(HtmlCleaner.clean_data(page_source, url).prettify())

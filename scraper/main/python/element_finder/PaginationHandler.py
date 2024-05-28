import logging
import time
import traceback
from enum import Enum

import regex
from selenium.common import ElementNotInteractableException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By
from num2words import num2words

from element_finder import BlockFinder
from scrapers import WebScraper
from scrapers.WebScraper import count_tags
from services import SettingsService

settings_service = SettingsService.service


def next_page(driver, soup, blocks, current_page, handler, interaction_buttons, failed_handlers, scraper_settings):
    """
    :return: HandlerType used to navigate to the next page. If no handler was used, returns None.
    """
    start_time = time.time()

    max_page = settings_service.get_catalog_setting('max_page_count')

    if current_page == max_page:
        logging.info(f"Reached max page count ({max_page})")
        return None

    logging.info(f"Attempting to navigate to page {current_page + 1}...")

    soup = soup.find('body')

    block_parent = get_block_parent(soup, blocks)

    soup = remove_blocks(soup, blocks)
    new_handler = None

    if try_infinite_scroll(driver, current_page, max_page, handler, failed_handlers, scraper_settings):
        new_handler = HandlerType.INFINITE_SCROLL
    elif try_click_paginator(driver, soup, current_page, blocks, block_parent,
                             interaction_buttons, handler, failed_handlers):
        new_handler = HandlerType.PAGINATOR
    elif try_click_view_more(driver, soup, blocks, block_parent, handler, interaction_buttons, failed_handlers):
        new_handler = HandlerType.VIEW_MORE
    else:
        logging.info(f"No more pages to navigate to. Current page: {current_page}")

    logging.info(f"PaginationHandler > Next page "
                 f"{'(initial discovery)' if handler is None else ''} "
                 f"{time.time() - start_time:.3f}s")

    return new_handler


def get_block_parent(soup, blocks):
    block_parent = None
    if len(blocks) > 0:
        block_parent = get_by_index(soup, blocks[0]['parent'])

    return block_parent


def get_by_index(soup, index):
    tag = soup.find(attrs={'scraper-index': index})
    return tag


def remove_blocks(soup, blocks):
    for block in blocks:
        index = block['index']
        tag = soup.find(attrs={'scraper-index': index})
        if tag is not None:
            tag.clear()

    return soup


def try_click_paginator(driver, soup, current_page, blocks, block_parent, interaction_buttons, handler, failed_handlers):
    if can_handle(handler, HandlerType.PAGINATOR, failed_handlers) is False:
        return False

    paginator_delay = settings_service.get_catalog_setting('paginator_delay')

    potential_buttons = find_potential_buttons(soup, current_page, blocks)

    if sum(len(buttons) for buttons in potential_buttons.values()) == 0:
        return False

    paginator_attempts = settings_service.get_catalog_setting('paginator_attempts')

    closest_button = get_paginator_button(potential_buttons, current_page, block_parent)

    if closest_button is None:
        return False

    result = click_button(driver, closest_button, interaction_buttons, paginator_attempts)

    if result is False:
        return False

    logging.info(f"[HandlerType=PAGINATOR] Clicked paginator on page {current_page}")

    time.sleep(paginator_delay)
    return True


def try_infinite_scroll(driver, current_page, max_page, handler, failed_handlers, scraper_settings):
    if can_handle(handler, HandlerType.INFINITE_SCROLL, failed_handlers) is False:
        return False

    scroll_time = settings_service.get_catalog_setting('scroll_delay')
    scroll_offset = settings_service.get_catalog_setting('scroll_offset')

    old_count = 0
    new_count = count_tags(driver, scraper_settings)
    height_changes = 0

    while old_count != new_count and current_page + height_changes <= max_page:
        height_changes += 1
        old_count = new_count

        actions = ActionChains(driver)
        actions.scroll_by_amount(0, 100000).perform()
        actions.scroll_by_amount(0, -scroll_offset).perform()

        for _ in range(scroll_time * 2):
            new_count = count_tags(driver, scraper_settings)
            if old_count != new_count:
                break
            time.sleep(0.5)

    if height_changes <= 2:
        return False
    logging.info(f"[HandlerType=INFINITE_SCROLL] Reached bottom of page {current_page}")

    return True


def find_potential_buttons(soup, current_page, blocks):
    max_page = settings_service.get_catalog_setting('max_page_count')

    potential_numbers = []

    if current_page > 2:
        potential_numbers.append(current_page - 2)
    if current_page > 1:
        potential_numbers.append(current_page - 1)

    potential_numbers.append(current_page)

    if current_page < max_page:
        potential_numbers.append(current_page + 1)
    if current_page < max_page - 1:
        potential_numbers.append(current_page + 2)

    potential_buttons = {}
    for number in potential_numbers:
        potential_buttons[number] = []

    for potential_number in potential_numbers:
        number_regex = regex.compile(f"(?<=^\\s*){potential_number}(?=\\s*$)")
        potential_strings = soup.find_all(string=number_regex)

        # Google Translate sometimes translates numbers to words in the paginator
        potential_number_words = num2words(potential_number)
        escaped_number_words = (regex.escape(potential_number_words)
                                .replace('\\-', '[\\-\\s]?'))
        word_regex = regex.compile(f"(?<=^\\s*){escaped_number_words}(?=\\s*$)")
        potential_strings.extend(soup.find_all(string=word_regex))

        for potential_string in potential_strings:
            potential_button = find_parent_button(potential_string.parent)
            if potential_button.name == 'script':
                continue
            if is_after_blocks(potential_button, blocks):
                potential_buttons[potential_number].append(potential_button)

    return potential_buttons


def is_after_blocks(button, blocks):
    if blocks is None or len(blocks) == 0:
        return True

    button_index = int(button['scraper-index'])
    last_block_index = int(blocks[-1]['tag']['scraper-index'])

    return button_index > last_block_index


def get_paginator_button(potential_buttons, current_page, block_parent):
    max_pagination_distance = settings_service.get_catalog_setting('max_pagination_distance')

    kept_buttons = {}
    current_buttons = potential_buttons[current_page]

    #  Find buttons that are close to the current page's buttons
    for current_button in current_buttons:
        for page, other_buttons in potential_buttons.items():
            for other_button in other_buttons:
                if BlockFinder.get_distance(current_button, other_button) <= max_pagination_distance:
                    if current_button not in kept_buttons:
                        kept_buttons[current_button] = {current_page: [current_button]}
                    if page not in kept_buttons[current_button]:
                        kept_buttons[current_button][page] = []
                    kept_buttons[current_button][page].append(other_button)

    buttons = []

    for group in kept_buttons.values():
        if current_page + 1 in group:
            buttons.extend(group[current_page + 1])

    labeled_paginator_buttons = check_for_paginator_class(buttons)
    if len(labeled_paginator_buttons) > 0:
        return find_closest(labeled_paginator_buttons, block_parent)

    closest_button = find_closest(buttons, block_parent)

    return closest_button


def check_for_paginator_class(buttons):
    paginator_classes = settings_service.get_catalog_setting('paginator_classes')
    paginator_levels = settings_service.get_catalog_setting('paginator_levels')

    found_buttons = []
    selector_regex = regex.compile(f"([^>]+>?){{{paginator_levels}}}$")
    for paginator_class in paginator_classes:
        class_regex = regex.compile(f"\\b{paginator_class}\\b", regex.IGNORECASE)
        for button in buttons:
            css_selector = get_css_selector(button)
            button_selector = regex.search(selector_regex, css_selector).group(0)

            if button_selector is None:
                continue

            if regex.search(class_regex, button_selector) is not None:
                found_buttons.append(button)

    return found_buttons


def click_button(driver, button, interaction_buttons, attempts):
    for attempt in range(attempts):
        found = try_click_button(driver, button, interaction_buttons)
        if found is True:
            return True
        if attempt < attempts - 1:
            time.sleep(1)

    return False


def try_click_button(driver, button, interaction_buttons=None, attempts=0):
    css_selector = ''
    try:
        if isinstance(button, str):
            css_selector = button
        else:
            css_selector = get_css_selector(button)

        element = driver.find_element(By.CSS_SELECTOR, css_selector)

        if attempts < 2:
            scroll_and_enter(driver, element)  # Does not require the element to be visible
        else:
            scroll_and_click(driver, element)

        logging.log(18, f"Clicked {css_selector}")
        return True
    except ElementNotInteractableException:
        logging.log(19, f"Element not intractable.")
        if attempts == 0:
            try_interaction_buttons(driver, interaction_buttons)
        elif attempts > 1:
            return False
        return try_click_button(driver, button, interaction_buttons, attempts + 1)
    except NoSuchElementException:
        iframes = WebScraper.try_get_iframes(driver)
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                continue

            result = try_click_button(driver, button, interaction_buttons, attempts)
            driver.switch_to.parent_frame()

            if result is True:
                return True
        return False
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.log(18, f"Exception while clicking button {css_selector}:\n{traceback.format_exc()}")
        return False


def scroll_and_enter(driver, button):
    move_to_element(driver, button)

    time.sleep(0.5)
    button.send_keys(Keys.ENTER)


def scroll_and_click(driver, button):
    move_to_element(driver, button)

    time.sleep(0.5)
    ActionChains(driver).click(button).perform()


def move_to_element(driver, element):
    try:
        scroll_by_coord = 'window.scrollTo(%s,%s);' % (
            element.location['x'],
            element.location['y'] - 324  # 324 is half of the set browser window height
        )
        driver.execute_script(scroll_by_coord)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        ActionChains(driver).move_to_element(element).perform()


def try_interaction_buttons(driver, interaction_buttons):
    if interaction_buttons is not None:
        logging.log(19, "Trying interaction buttons...")
        for interaction_button in interaction_buttons:
            try:
                return try_click_button(driver, interaction_button)
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                continue
    return False


def get_css_selector(tag):
    css_selector = ''
    while tag.parent is not None:
        tag_number = 1
        tag_count = 0
        found_id = tag.attrs.get('id')

        if found_id is not None:
            if len(css_selector) == 0:
                return f'#{found_id}'
            css_selector = f'#{found_id}{css_selector}'
            return css_selector

        if tag.parent is not None:
            for sibling in tag.parent.children:
                if sibling.name == tag.name:
                    tag_count += 1
                    if sibling == tag:
                        tag_number = tag_count
                        break

        class_list = format_class_list(tag)

        tag_index_string = ''
        try:
            similar_tags = tag.parent.select(f"{tag.name}{class_list}")
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except NotImplementedError:
            logging.error(f"{traceback.format_exc()} \n CSS selector not implemented for \n {tag}")
            similar_tags = []
        if len(similar_tags) > 1:
            tag_index_string = f":nth-of-type({tag_number})"

        css_selector = f'>{tag.name}{class_list}{tag_index_string}{css_selector}'

        tag = tag.parent

    return css_selector[1:]


def format_class_list(tag):
    class_list = tag.attrs.get('class')
    if class_list is None:
        return ''

    formatted_class_list = ''
    restricted_class_symbols = settings_service.get_webscraper_setting('restricted_class_symbols')

    for class_name in class_list:
        class_name = class_name.replace(' ', '')

        for symbol in restricted_class_symbols:
            class_name = class_name.replace(symbol, f'\\{symbol}')
        class_name = regex.sub(r'^[0-9]', '', class_name)

        if len(class_name) > 0:
            formatted_class_list += f'.{class_name}'
    return formatted_class_list


def try_click_view_more(driver, soup, blocks, block_parent, handler, interaction_buttons, failed_handlers):
    if can_handle(handler, HandlerType.VIEW_MORE, failed_handlers) is False:
        return False

    view_more_aliases = settings_service.get_catalog_setting('view_more_aliases')
    view_more_attempts = settings_service.get_catalog_setting('view_more_attempts')
    view_more_load_delay = settings_service.get_catalog_setting('view_more_load_delay')

    view_more_buttons = []

    for alias in view_more_aliases:
        alias_regex = regex.compile(f"\\b{alias}\\b", regex.IGNORECASE)
        strings = soup.find_all(string=alias_regex)

        for string in strings:
            tag = string.parent
            button = find_parent_button(tag)
            if is_after_blocks(button, blocks) and is_valid_link(button, driver):
                view_more_buttons.append(button)

    closest_button = find_closest(view_more_buttons, block_parent)

    if closest_button is None:
        return False

    result = click_button(driver, closest_button, interaction_buttons, view_more_attempts)

    if result is False:
        return False

    logging.info(f"[HandlerType=VIEW_MORE] Clicked view more")

    time.sleep(view_more_load_delay)
    return True


def find_parent_button(tag):
    pagination_tags = settings_service.get_catalog_setting('pagination_tags')

    if tag.name in pagination_tags:
        return tag

    parent = tag.parent
    for _ in range(5):
        if parent.name in pagination_tags:
            return parent
        parent = parent.parent
        if parent is None:
            break

    return tag


def is_valid_link(button, driver):
    if button.name != 'a' or button.attrs is None:
        return True

    href = button.attrs.get('href')
    if href is None:
        return True

    current_url = driver.current_url

    domain_regex = regex.compile("(?<=(www\\.|https?:\\/\\/))[^/]+(?=\\.)")
    current_domain = regex.search(domain_regex, current_url)
    href_domain = regex.search(domain_regex, href)

    if (current_url.endswith(href) or
            (href_domain is not None and current_domain.group(0) != href_domain.group(0))):
        return False

    return True


def find_closest(buttons, block_parent):
    if block_parent is None and len(buttons) > 0:
        return buttons[0]

    closest_button = None
    closest_distance = 999
    for button in buttons:
        distance = BlockFinder.get_distance(button, block_parent)
        if distance < closest_distance:
            closest_button = button
            closest_distance = distance

    return closest_button


def can_handle(handler, handler_type, failed_handlers):
    return (handler is None or handler is handler_type) and handler_type not in failed_handlers


class HandlerType(Enum):
    INFINITE_SCROLL = 1
    PAGINATOR = 2
    VIEW_MORE = 3

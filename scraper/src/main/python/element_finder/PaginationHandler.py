import logging
import time
import traceback
from enum import Enum

import regex
from bs4 import BeautifulSoup
from selenium.common import ElementNotInteractableException
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By

from element_finder import BlockFinder
from preprocessing import HtmlCleaner
from scrapers.WebScraper import count_tags
from services import SettingsService

SettingsService = SettingsService.service


def next_page(driver, page_source, blocks, current_page, handler, interaction_buttons):
    scroll_time = SettingsService.get_catalog_setting('scroll_delay')
    max_page = SettingsService.get_catalog_setting('max_page_count')

    if current_page == max_page:
        logging.info(f"Reached max page count ({max_page})")
        return None, current_page

    soup = BeautifulSoup(page_source, 'html.parser')
    HtmlCleaner.add_tag_indexes(soup)

    soup = soup.find('body')

    if len(blocks) > 0:
        block_parent = get_by_index(soup, blocks[0]['parent'])
        soup = remove_blocks(soup, blocks)
    else:
        block_parent = None

    is_infinite_scroll, current_page = scroll_to_bottom(driver, scroll_time, current_page, handler, max_page)
    if is_infinite_scroll:
        logging.info(f"[HandlerType=INFINITE_SCROLL] Reached bottom of page {current_page}")
        return HandlerType.INFINITE_SCROLL, current_page

    if try_click_paginator(driver, soup, current_page, blocks, block_parent, handler, interaction_buttons):
        paginator_delay = SettingsService.get_catalog_setting('paginator_delay')
        time.sleep(paginator_delay)
        logging.info(f"[HandlerType=PAGINATOR] Clicked paginator on page {current_page}")

        return HandlerType.PAGINATOR, current_page

    is_view_more, current_page = try_click_view_more(driver, soup, current_page, blocks, block_parent, handler, max_page,
                                                     interaction_buttons)
    if is_view_more is True:
        logging.info(f"[HandlerType=VIEW_MORE] Clicked view more on page {current_page}")
        return HandlerType.VIEW_MORE, current_page

    logging.info(f"[HandlerType=LIST] Reached end of page {current_page}")
    return HandlerType.LIST, current_page


def get_tag(soup, block):
    index = block['index']
    tag = get_by_index(soup, index)
    return tag


def get_by_index(soup, index):
    tag = soup.find(attrs={'scraper-index': index})
    return tag


def scroll_to_bottom(driver, delay, current_page, handler, max_page):
    if can_handle(handler, HandlerType.INFINITE_SCROLL) is False:
        return False, current_page

    scroll_offset = SettingsService.get_catalog_setting('scroll_offset')

    old_count = 0
    new_count = count_tags(driver.page_source)
    height_changes = 0

    while old_count != new_count and current_page + height_changes <= max_page:
        height_changes += 1
        old_count = new_count

        actions = ActionChains(driver)
        actions.scroll_by_amount(0, 100000).perform()
        actions.scroll_by_amount(0, -scroll_offset).perform()

        for _ in range(delay * 2):
            new_count = count_tags(driver.page_source)
            if old_count != new_count:
                break
            time.sleep(0.5)

    if height_changes > 2:
        return True, current_page + height_changes - 1
    return False, current_page


def remove_blocks(soup, blocks):
    for block in blocks:
        index = block['index']
        tag = soup.find(attrs={'scraper-index': index})
        if tag is not None:
            tag.clear()

    return soup


def try_click_paginator(driver, soup, current_page, blocks, block_parent, handler, interaction_buttons):
    if can_handle(handler, HandlerType.PAGINATOR) is False:
        return False

    potential_buttons = find_potential_buttons(soup, current_page, blocks)

    if len(potential_buttons) == 0:
        return False

    paginator_attempts = SettingsService.get_catalog_setting('paginator_attempts')

    if len(potential_buttons[current_page + 1]) == 1:
        result = click_button(driver, potential_buttons[current_page + 1][0], interaction_buttons, paginator_attempts)
        return result

    closest_button = get_paginator_button(potential_buttons, current_page, block_parent)
    if closest_button is not None:
        result = click_button(driver, closest_button, interaction_buttons, paginator_attempts)
        return result
    return False


def find_potential_buttons(soup, current_page, blocks):
    max_page = SettingsService.get_catalog_setting('max_page_count')

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

        for potential_string in potential_strings:
            potential_button = find_parent_button(potential_string.parent)
            if is_after_blocks(potential_button, blocks):
                potential_buttons[potential_number].append(potential_button)

    return potential_buttons


def is_after_blocks(button, blocks):
    if blocks is None or len(blocks) == 0:
        return True

    button_index = int(button['scraper-index'])
    last_block_index = int(blocks[-1]['tag']['scraper-index'])

    return button_index > last_block_index


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


def get_paginator_button(potential_buttons, current_page, block_parent):
    max_pagination_distance = SettingsService.get_catalog_setting('max_pagination_distance')

    kept_buttons = {}
    current_buttons = potential_buttons[current_page]

    for current_button in current_buttons:
        for page, other_buttons in potential_buttons.items():
            for other_button in other_buttons:
                if BlockFinder.get_distance(current_button, other_button) <= max_pagination_distance:
                    if current_button not in kept_buttons:
                        kept_buttons[current_button] = {current_page: current_button}
                    kept_buttons[current_button][page] = other_button

    buttons = []

    for group in kept_buttons.values():
        if current_page + 1 in group:
            buttons.append(group[current_page + 1])

    labeled_paginator_buttons = check_for_paginator_class(buttons)
    if len(labeled_paginator_buttons) > 0:
        return find_closest(labeled_paginator_buttons, block_parent)

    closest_button = find_closest(buttons, block_parent)

    return closest_button


def check_for_paginator_class(buttons):
    paginator_classes = SettingsService.get_catalog_setting('paginator_classes')
    paginator_levels = SettingsService.get_catalog_setting('paginator_levels')

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


def try_click_button(driver, button, interaction_buttons, attempts=0):
    try:
        css_selector = get_css_selector(button)
        element = driver.find_element(By.CSS_SELECTOR, css_selector)

        scroll_and_click(driver, element)

        logging.log(18, f"Clicked {css_selector}")
        return True
    except ElementNotInteractableException:
        if attempts > 0:
            return False
        logging.log(19, f"Element not interactable.")
        try_interaction_buttons(driver, interaction_buttons)
        return try_click_button(driver, button, interaction_buttons, attempts + 1)
    except:
        logging.log(18, f"Exception while clicking:\n{traceback.format_exc()}")
        return False


def scroll_and_click(driver, button):
    actions = ActionChains(driver)
    actions.move_to_element(button).perform()

    button.send_keys(Keys.ENTER)


def try_interaction_buttons(driver, interaction_buttons):
    if interaction_buttons is not None:
        logging.log(19, "Trying interaction buttons...")
        for interaction_button in interaction_buttons:
            try:
                element = driver.find_element(By.CSS_SELECTOR, interaction_button)
                scroll_and_click(driver, element)
                return True
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
        similar_tags = tag.parent.select(f"{tag.name}{class_list}")
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
    for class_name in class_list:
        formatted_class_list += f'.{class_name}'
    return formatted_class_list


def find_parent_button(tag):
    pagination_tags = SettingsService.get_catalog_setting('pagination_tags')

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


def try_click_view_more(driver, soup, current_page, blocks, block_parent, handler, max_page, interaction_buttons):
    if can_handle(handler, HandlerType.VIEW_MORE) is False:
        return False, current_page

    view_more_aliases = SettingsService.get_catalog_setting('view_more_aliases')
    view_more_attempts = SettingsService.get_catalog_setting('view_more_attempts')
    view_more_load_all = SettingsService.get_catalog_setting('view_more_load_all')
    view_more_load_delay = SettingsService.get_catalog_setting('view_more_load_delay')

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

    if closest_button is not None:
        times_clicked = 0
        result = click_button(driver, closest_button, interaction_buttons, view_more_attempts)

        if view_more_load_all is True:
            while result and current_page + times_clicked <= max_page and is_valid_link(closest_button, driver):
                time.sleep(view_more_load_delay)
                times_clicked += 1
                result = click_button(driver, closest_button, interaction_buttons, view_more_attempts)

        current_page += times_clicked
        return times_clicked > 0 or result, current_page

    return False, current_page


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


def can_handle(handler, handler_type):
    return handler is None or handler is handler_type


class HandlerType(Enum):
    LIST = 1
    INFINITE_SCROLL = 2
    PAGINATOR = 3
    VIEW_MORE = 4

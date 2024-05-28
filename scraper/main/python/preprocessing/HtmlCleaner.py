import timeit
import traceback

import regex
import logging

from bs4 import BeautifulSoup, Comment
from bs4 import NavigableString
import css_inline
from premailer import Premailer

from scrapers.ScraperSettings import ScraperSettings
from services import SettingsService

settings_service = SettingsService.service


def clean_data(soup, scraper_settings: ScraperSettings):
    inlined_source = inline_css(str(soup), scraper_settings)

    soup = make_soup(inlined_source)

    inline_images(soup, scraper_settings)

    remove_comments(soup, scraper_settings)
    remove_invisible_tags(soup, scraper_settings)
    remove_excluded_tags(soup, scraper_settings)
    remove_non_whitelisted_attributes(soup, scraper_settings)

    flatten_text(soup, scraper_settings)
    flatten_special_strings(soup, scraper_settings)

    remove_redundant_punctuation(soup, scraper_settings)
    remove_punctuation_whitespace(soup, scraper_settings)
    remove_duplicate_whitespace(soup, scraper_settings)
    remove_empty_tags(soup, scraper_settings)

    return soup


def remove_comments(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_comments' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()

    logging.log(19, f"HtmlCleaner > Remove comments {timeit.default_timer() - start:.3f}s")


def inline_css(page_source, scraper_settings):
    start = timeit.default_timer()

    if 'inline_css' in scraper_settings.configuration.ignored_cleaning_steps:
        return page_source

    inliner = css_inline.CSSInliner(base_url=scraper_settings.url, preallocate_node_capacity=1500)

    try:
        inlined_source = inliner.inline(page_source)
        return inlined_source
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.info("Issue inlining CSS with CSSInliner. Trying Premailer...")
        logging.log(18, f"HtmlCleaner > Inline CSS with CSSInliner failed: {traceback.format_exc()}")
        return inline_css_old(page_source, scraper_settings)
    finally:
        logging.log(19, f"HtmlCleaner > Inline CSS {timeit.default_timer() - start:.3f}s")


def inline_css_old(page_source, scraper_settings):
    if 'inline_css' in scraper_settings.configuration.ignored_cleaning_steps:
        return page_source

    logging.disable(logging.ERROR)  # premailer warnings/errors can be ignored
    premailer = Premailer(page_source,
                          base_url=scraper_settings.url,
                          include_star_selectors=True,
                          allow_loading_external_files=True,
                          disable_validation=True,
                          allow_insecure_ssl=True,
                          cache_css_parsing=True,
                          disable_leftover_css=True, )

    try:
        result = premailer.transform(pretty_print=False)
        logging.disable(logging.NOTSET)
        logging.info(f"Inlining with Premailer was successful")
        return result
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.disable(logging.NOTSET)
        logging.warning(
            f"Error inlining CSS with Premailer: {traceback.format_exc()}\nReturning original page source...")
        return page_source


def make_soup(source):
    start = timeit.default_timer()

    soup = BeautifulSoup(source, 'html.parser')
    body = soup.find('body')

    logging.log(19, f"HtmlCleaner > Make soup for cleaning {timeit.default_timer() - start:.3f}s")

    return body


def remove_excluded_tags(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_excluded_tags' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    excluded_tags = settings_service.get_scraper_setting('excluded_tags', scraper_settings.scraper_type)
    for excluded_tag in excluded_tags:
        for tag in soup.select(excluded_tag):
            tag.replace_with('\n')

    logging.log(19, f"HtmlCleaner > Remove excluded tags {timeit.default_timer() - start:.3f}s")


def remove_invisible_tags(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_invisible_tags' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    for invisible_tag in settings_service.get_scraper_setting('invisible_tag_regex', scraper_settings.scraper_type):
        remove_tags_by_criteria(soup, style=regex.compile(invisible_tag))
    remove_tags_by_criteria(soup, hidden=True)

    logging.log(19, f"HtmlCleaner > Remove invisible tags {timeit.default_timer() - start:.3f}s")


def remove_tags_by_criteria(soup, **kwargs):
    for hidden_tag in soup.find_all(**kwargs):
        hidden_tag.extract()


def remove_non_whitelisted_attributes(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_non_whitelisted_attributes' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    whitelisted_attributes = settings_service.get_scraper_setting('whitelisted_attributes', scraper_settings.scraper_type)
    whitelisted_attributes.append('scraper-index')

    for tag in soup.find_all():
        try:
            remaining_attrs = {}
            for attr in tag.attrs:
                if attr in whitelisted_attributes:
                    remaining_attrs[attr] = tag.attrs[attr]
            tag.attrs = remaining_attrs
        except AttributeError:
            pass

    logging.log(19, f"HtmlCleaner > Remove non-whitelisted attributes {timeit.default_timer() - start:.3f}s")


def flatten_text(soup, scraper_settings):
    start = timeit.default_timer()

    if 'flatten_text' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    flattened_tags = settings_service.get_scraper_setting('flattened_tags', scraper_settings.scraper_type)
    for flattened_tag in flattened_tags:
        for tag in soup.select(flattened_tag):
            if isinstance(tag, NavigableString):
                clean_extract(tag)
            else:
                all_flattenable_children = True
                for child in tag.find_all():
                    if child.name not in flattened_tags:
                        all_flattenable_children = False
                        break

                if all_flattenable_children:
                    clean_extract(tag)

    logging.log(19, f"HtmlCleaner > Flatten text {timeit.default_timer() - start:.3f}s")


def flatten_special_strings(soup, scraper_settings):
    start = timeit.default_timer()

    if 'flatten_special_strings' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    flattened_special_strings = settings_service.get_scraper_setting('flattened_special_strings', scraper_settings.scraper_type)
    for flattened_special_string in flattened_special_strings:
        for string in soup.find_all(string=flattened_special_string):
            tag = string.parent
            for child in list(tag.parent.children).copy():
                clean_extract(child)

    logging.log(19, f"HtmlCleaner > Flatten special strings {timeit.default_timer() - start:.3f}s")


def inline_images(soup, scraper_settings):
    start = timeit.default_timer()

    if 'inline_images' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    url_regex = regex.compile('(?<=url\\(["\'])(.*?)(?=["\']\\))')
    for tag in soup.find_all(style=regex.compile('background(-image)?')):
        style = tag.attrs['style']
        image_url = regex.search(url_regex, style)

        if image_url is None:
            continue

        temp_soup = BeautifulSoup(f'<img src="{image_url.group()}"/>', 'lxml')
        new_tag = temp_soup.html.body.contents[0]

        tag.append(new_tag)

    logging.log(19, f"HtmlCleaner > Inline images {timeit.default_timer() - start:.3f}s")


def remove_empty_tags(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_empty_tags' in scraper_settings.configuration.ignored_cleaning_steps:
        return
    empty_tags = settings_service.get_scraper_setting('empty_tags', scraper_settings.scraper_type)

    tags = soup.find_all()
    for tag in tags:
        if tag is None:
            continue
        if count_contents(tag) == 0 and tag.name not in empty_tags:
            tags.append(tag.parent)
            clean_extract(tag)

    logging.log(19, f"HtmlCleaner > Remove empty tags {timeit.default_timer() - start:.3f}s")


def count_contents(tag):
    count = 0
    for content in tag.contents:
        if type(content) is NavigableString:
            if not is_empty(content):
                count += 1
        else:
            count += 1

    return count


def is_empty(tag):
    empty_regex = regex.compile('[\n\\s\\t\\r\\v\\f]')
    if isinstance(tag, NavigableString):
        return len(regex.sub(empty_regex, '', tag)) == 0
    else:
        return len(tag.contents) == 0


def clean_extract(tag):
    parent = tag.parent
    if parent is None:
        return
    tag_index = parent.contents.index(tag)
    rez_text = tag.text.strip()

    if (tag_index < len(parent.contents) - 1
            and isinstance(parent.contents[tag_index + 1], NavigableString)):
        rez_text = join_if_present(rez_text, parent.contents[tag_index + 1].text)
        parent.contents[tag_index + 1].extract()

    if (tag_index > 0
            and isinstance(parent.contents[tag_index - 1], NavigableString)):
        rez_text = join_if_present(parent.contents[tag_index - 1].text, rez_text)
        parent.contents[tag_index - 1].extract()

    if len(rez_text) > 0:
        tag.replace_with(rez_text)
    else:
        tag.extract()


def join_if_present(a, b):
    if len(a) > 0 and len(b) > 0:
        return f"{a.strip()} {b.strip()}"
    elif len(a) > 0:
        return a.strip()
    elif len(b) > 0:
        return b.strip()
    else:
        return ''


def remove_duplicate_whitespace(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_duplicate_whitespace' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    whitespace_regex = regex.compile(r'[\s\n\r\t\v\f\0]+')
    found_tags = soup.find_all(string=whitespace_regex)

    for tag in found_tags:
        rez_text = whitespace_regex.sub(' ', tag)
        tag.replace_with(rez_text)

    logging.log(19, f"HtmlCleaner > Remove duplicate whitespace {timeit.default_timer() - start:.3f}s")


def remove_punctuation_whitespace(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_punctuation_whitespace' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    punctuation_marks = settings_service.get_scraper_setting('punctuation_marks', scraper_settings.scraper_type)
    for punctuation_mark in punctuation_marks:
        punctuation_regex = regex.compile(f'\\s+{regex.escape(punctuation_mark)}')
        found_tags = soup.find_all(string=punctuation_regex)

        for tag in found_tags:
            rez_text = punctuation_regex.sub(punctuation_mark, tag)
            tag.replace_with(rez_text)

    logging.log(19, f"HtmlCleaner > Remove punctuation whitespace {timeit.default_timer() - start:.3f}s")


def remove_redundant_punctuation(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_redundant_punctuation' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    redundant_punctuation_marks = settings_service.get_scraper_setting('redundant_punctuation_marks', scraper_settings.scraper_type)
    for punctuation_mark in redundant_punctuation_marks:
        punctuation_regex = regex.compile(f'\\s*{regex.escape(punctuation_mark)}\\s*')
        found_tags = soup.find_all(string=punctuation_regex)

        for tag in found_tags:
            rez_text = punctuation_regex.sub(' ', tag)
            tag.replace_with(rez_text)

    logging.log(19, f"HtmlCleaner > Remove redundant punctuation {timeit.default_timer() - start:.3f}s")
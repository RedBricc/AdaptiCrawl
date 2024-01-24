import timeit
import traceback

import regex
import logging

from bs4 import BeautifulSoup, Comment
from bs4 import NavigableString
import css_inline
from premailer import Premailer

from services import SettingsService
from services import StopwordService

SettingsService = SettingsService.service
StopwordService = StopwordService.service


def clean_data(page_source, url, ignored_cleaning_steps):
    # Make soup
    start = timeit.default_timer()
    soup = BeautifulSoup(page_source, 'html.parser')
    logging.log(19, f"HtmlCleaner > Make soup for indexes {timeit.default_timer() - start}")

    # Add tag indexes
    start = timeit.default_timer()
    add_tag_indexes(soup)
    logging.log(19, f"HtmlCleaner > Add tag indexes {timeit.default_timer() - start}")

    # Inline CSS
    start = timeit.default_timer()
    inlined_source = inline_css(str(soup), url, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Inline CSS {timeit.default_timer() - start}")

    # Make soup again
    start = timeit.default_timer()
    soup = BeautifulSoup(inlined_source, 'html.parser')
    body = soup.find('body')
    logging.log(19, f"HtmlCleaner > Make soup for cleaning {timeit.default_timer() - start}")

    # Remove comments
    start = timeit.default_timer()
    remove_comments(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove comments {timeit.default_timer() - start}")

    # Remove invisible tags
    start = timeit.default_timer()
    remove_invisible_tags(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove invisible tags {timeit.default_timer() - start}")

    # Remove excluded tags
    start = timeit.default_timer()
    remove_excluded_tags(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove excluded tags {timeit.default_timer() - start}")

    # Remove non-whitelisted attributes
    start = timeit.default_timer()
    remove_non_whitelisted_attributes(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove non-whitelisted attributes {timeit.default_timer() - start}")

    # Flatten text
    start = timeit.default_timer()
    flatten_text(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Flatten text {timeit.default_timer() - start}")

    # Flatten special strings
    start = timeit.default_timer()
    flatten_special_strings(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Flatten special strings {timeit.default_timer() - start}")

    # Remove duplicate whitespace
    start = timeit.default_timer()
    remove_duplicate_whitespace(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove duplicate whitespace {timeit.default_timer() - start}")

    # Remove punctuation whitespace
    start = timeit.default_timer()
    remove_punctuation_whitespace(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove punctuation whitespace {timeit.default_timer() - start}")

    # Remove stopwords
    do_stopwords = SettingsService.get_catalog_setting('stopwords_enabled')
    if do_stopwords is True:
        start = timeit.default_timer()
        remove_stopwords(body, ignored_cleaning_steps)
        logging.log(19, f"HtmlCleaner > Remove stopwords {timeit.default_timer() - start}")

    # Remove empty tags
    start = timeit.default_timer()
    remove_empty_tags(body, ignored_cleaning_steps)
    logging.log(19, f"HtmlCleaner > Remove empty tags {timeit.default_timer() - start}")

    return body


def add_tag_indexes(soup):
    for index, tag in enumerate(soup.find_all()):
        tag.attrs['scraper-index'] = index


def remove_comments(soup, ignored_cleaning_steps=()):
    if 'remove_comments' in ignored_cleaning_steps:
        return
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()


def inline_css(page_source, url, ignored_cleaning_steps=()):
    if 'inline_css' in ignored_cleaning_steps:
        return page_source

    inliner = css_inline.CSSInliner(base_url=url, preallocate_node_capacity=1500)

    try:
        inlined_source = inliner.inline(page_source)
        return inlined_source
    except:
        logging.info("Issue inlining CSS with CSSInliner. Trying Premailer...")
        logging.log(19, f"HtmlCleaner > Inline CSS with CSSInliner failed: {traceback.format_exc()}")
        return inline_css_old(page_source, url, ignored_cleaning_steps)


def inline_css_old(page_source, url, ignored_cleaning_steps=()):
    if 'inline_css' in ignored_cleaning_steps:
        return page_source

    logging.disable(logging.ERROR)  # premailer warnings/errors can be ignored
    premailer = Premailer(page_source,
                          base_url=url,
                          include_star_selectors=True,
                          allow_loading_external_files=True,
                          disable_validation=True,
                          cache_css_parsing=True,
                          disable_leftover_css=True,)

    try:
        result = premailer.transform(pretty_print=False)
        logging.disable(logging.NOTSET)
        logging.info(f"Inlining with Premailer was successful")
        return result
    except:
        logging.disable(logging.NOTSET)
        logging.warning(f"Error inlining CSS with Premailer: {traceback.format_exc()}\nReturning original page source...")
        return page_source


def remove_excluded_tags(soup, ignored_cleaning_steps=()):
    if 'remove_excluded_tags' in ignored_cleaning_steps:
        return
    for excluded_tag in SettingsService.get_catalog_setting('excluded_tags'):
        for tag in soup.select(excluded_tag):
            tag.extract()


def remove_invisible_tags(soup, ignored_cleaning_steps=()):
    if 'remove_invisible_tags' in ignored_cleaning_steps:
        return
    for invisible_tag in SettingsService.get_catalog_setting('invisible_tag_regex'):
        remove_tags_by_criteria(soup, style=regex.compile(invisible_tag))
    remove_tags_by_criteria(soup, hidden=True)


def remove_tags_by_criteria(soup, **kwargs):
    for hidden_tag in soup.find_all(**kwargs):
        hidden_tag.extract()


def remove_stopwords(soup, ignored_cleaning_steps=()):
    stopwords = StopwordService.get_stopwords()
    for stopword in stopwords:
        stopword_regex = regex.compile(regex.escape(stopword), regex.IGNORECASE)
        found_tags = soup.find_all(string=stopword_regex)

        for tag in found_tags:
            rez_text = stopword_regex.sub('', tag).strip()
            tag.replace_with(rez_text)


def remove_non_whitelisted_attributes(soup, ignored_cleaning_steps=()):
    whitelisted_attributes = SettingsService.get_catalog_setting('whitelisted_attributes')
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


def flatten_text(soup, ignored_cleaning_steps=()):
    flattened_tags = SettingsService.get_catalog_setting('flattened_tags')
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


def flatten_special_strings(soup, ignored_cleaning_steps=()):
    flattened_special_strings = SettingsService.get_catalog_setting('flattened_special_strings')
    for flattened_special_string in flattened_special_strings:
        for string in soup.find_all(string=flattened_special_string):
            tag = string.parent
            for child in tag.parent.children:
                clean_extract(child)


def remove_empty_tags(soup, ignored_cleaning_steps=()):
    empty_tags = SettingsService.get_catalog_setting('empty_tags')

    tags = soup.find_all()
    for tag in tags:
        if tag is None:
            continue
        if count_contents(tag) == 0 and tag.name not in empty_tags:
            tags.append(tag.parent)
            clean_extract(tag)


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
        return f"{a} {b}"
    elif len(a) > 0:
        return a
    elif len(b) > 0:
        return b
    else:
        return ''


def remove_duplicate_whitespace(soup, ignored_cleaning_steps=()):
    whitespace_regex = regex.compile(r'\s{2,}')
    found_tags = soup.find_all(string=whitespace_regex)

    for tag in found_tags:
        rez_text = whitespace_regex.sub(' ', tag)
        tag.replace_with(rez_text)


def remove_punctuation_whitespace(soup, ignored_cleaning_steps=()):
    punctuation_marks = SettingsService.get_catalog_setting('punctuation_marks')
    for punctuation_mark in punctuation_marks:
        punctuation_regex = regex.compile(f'\\s+{regex.escape(punctuation_mark)}')
        found_tags = soup.find_all(string=punctuation_regex)

        for tag in found_tags:
            rez_text = punctuation_regex.sub(punctuation_mark, tag)
            tag.replace_with(rez_text)

import logging
import timeit

import regex

from services.StopwordService import StopwordService


# Unused, intended for use with classifiers. May be used in the future.
def soup_to_corpus(soup):
    empty_regex = regex.compile('[\\s\\t\\r\\v\\f]{2,}')
    newline_regex = regex.compile('\n+')
    text = ''

    for tag in soup:
        if len(tag.text.strip()) > 0:
            text += tag.text.strip()

    formatted_text = regex.sub(empty_regex, ' ', text)
    formatted_text = regex.sub(newline_regex, ' ', formatted_text)

    return [formatted_text]


def remove_stopwords(soup, scraper_settings):
    start = timeit.default_timer()

    if 'remove_stopwords' in scraper_settings.configuration.ignored_cleaning_steps:
        return

    stopwords = StopwordService.get_stopwords()
    for stopword in stopwords:
        stopword_regex = regex.compile(regex.escape(stopword), regex.IGNORECASE)
        found_tags = soup.find_all(string=stopword_regex)

        for tag in found_tags:
            rez_text = stopword_regex.sub('', tag).strip()
            tag.replace_with(rez_text)

    logging.log(19, f"Remove stopwords {timeit.default_timer() - start:.3f}s")

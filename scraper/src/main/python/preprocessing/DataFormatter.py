import regex


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

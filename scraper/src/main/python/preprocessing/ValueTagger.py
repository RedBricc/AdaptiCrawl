import json
import logging
import traceback

import regex
from bs4 import NavigableString

from services import SettingsService

SettingsService = SettingsService.service


def tag_values(soup):
    rules = SettingsService.get_catalog_setting('attribute_rules')

    for rule in rules:
        tags = rule.get('tags')

        # Can be both text and attribute
        if 'example_driven' in tags:
            if 'text' in tags:
                example_replace_text(soup, rule)
            if 'attribute' in tags:
                example_replace_attributes(soup, rule)
        if 'regex_driven' in tags:
            if 'text' in tags:
                regex_replace_text(soup, rule)
            if 'attribute' in tags:
                regex_replace_attributes(soup, rule)

    return soup


def example_replace_text(soup, rule):
    label = rule.get('name')
    examples = rule.get('examples')

    for example in examples:
        input_regex = f"\\b{regex.escape(str(example))}\\b"
        example_regex = compile_regex(rule, input_regex)
        found_tags = soup.find_all(string=example_regex)

        for tag in found_tags:
            if 'exclusive' in rule.get('tags'):
                label_regex = compile_regex(rule, f"\\b{regex.escape(label)}\\b")
                if regex.search(label_regex, tag):
                    continue

            filter_regex = None
            if 'filtered' in rule.get('tags'):
                filter_regex = compile_regex(rule, rule.get('filter_regex'))

            replace_text(example_regex, label, tag, filter_regex, rule)

    return soup


def regex_replace_text(soup, rule):
    label = rule.get('name')

    input_regex = rule.get('regex')
    value_regex = compile_regex(rule, input_regex)
    found_tags = soup.find_all(string=value_regex)
    similar_examples = []

    for tag in found_tags:
        filter_regex = None
        if 'filtered' in rule.get('tags'):
            filter_regex = compile_regex(rule, rule.get('filter_regex'))

        examples = replace_text(value_regex, label, tag, filter_regex, rule)
        if 'replace_similar' in rule.get('tags'):
            similar_examples.append(examples)

    if 'replace_similar' in rule.get('tags'):
        similar_rule = format_similar_rule(rule, similar_examples)
        example_replace_text(soup, similar_rule)

    return soup


def replace_text(target_regex, label, tag, filter_regex, rule):
    found_text = regex.search(target_regex, tag).group(0)

    if filter_regex is not None:
        found_text = filter_result(found_text, filter_regex)

    if len(found_text) == 0:
        return None

    formatted_label = format_label(label)
    rez_text = regex.sub(target_regex, formatted_label, tag).strip()

    add_data_attribute(tag, label, found_text, rule)
    tag.replace_with(rez_text)

    return found_text


def example_replace_attributes(soup, rule):
    label = rule.get('name')
    attribute_regex = regex.compile(rule.get('attribute_regex'))
    examples = rule.get('examples')

    for example in examples:
        input_regex = f"\\b{regex.escape(example)}\\b"
        example_regex = compile_regex(rule, input_regex)

        filter_regex = None
        if 'filtered' in rule.get('tags'):
            filter_regex = compile_regex(rule, rule.get('filter_regex'))

        replace_attributes(soup, attribute_regex, example_regex, label, filter_regex, rule)

    return soup


def regex_replace_attributes(soup, rule):
    label = rule.get('name')
    attribute_regex = regex.compile(rule.get('attribute_regex'))

    input_regex = rule.get('regex')
    value_regex = compile_regex(rule, input_regex)

    filter_regex = None
    if 'filtered' in rule.get('tags'):
        filter_regex = compile_regex(rule, rule.get('filter_regex'))

    similar_examples = replace_attributes(soup, attribute_regex, value_regex, label, filter_regex, rule)

    if 'replace_similar' in rule.get('tags'):
        similar_rule = format_similar_rule(rule, similar_examples)
        example_replace_attributes(soup, similar_rule)

    return soup


def format_similar_rule(rule, similar_examples):
    similar_rule = {
        'name': rule.get('name'),
        'tags': ['example_driven'],
        'examples': similar_examples,
    }

    tags = rule.get('tags')

    for tag in tags:
        if tag in ['ignore_case', 'exclusive', 'attribute', 'text']:
            similar_rule['tags'].append(tag)

    if 'attribute' in tags:
        similar_rule['attribute_regex'] = rule.get('attribute_regex')

    return similar_rule


def replace_attributes(soup, attribute_regex, target_regex, label, filter_regex, rule):
    similar_examples = []

    for tag in soup.find_all():
        try:
            attributes = tag.attrs.copy()

            for attr in attributes:
                if not regex.search(attribute_regex, attr):
                    continue

                attr_value = tag.attrs[attr]
                search_result = regex.search(target_regex, attr_value)

                if search_result is not None:
                    found_text = search_result.group(0)

                    if filter_regex is not None:
                        found_text = filter_result(found_text, filter_regex)

                    if len(found_text) == 0:
                        continue

                    add_data_attribute(tag, label, found_text, rule)

                    formatted_label = format_label(label)
                    tag.attrs[attr] = attr_value.replace(found_text, formatted_label).strip()

                    if 'replace_similar' in rule.get('tags'):
                        similar_examples.append(found_text)
        except AttributeError:
            logging.log(19, f"Exception while replacing attributes in {tag}\n{traceback.format_exc()}")

    return similar_examples


def filter_result(result, filter_regex):
    search = regex.search(filter_regex, result)
    if search is None:
        return result

    first_pos = search.start()
    filtered_result = result[:first_pos].strip()

    return filtered_result


def add_data_attribute(tag, label, data, rule):
    if isinstance(tag, NavigableString):
        tag = tag.parent

    attr_name = 'scraper-data'
    count_attribute = 'scraper-counts'

    if 'fallback' in rule.get('tags'):
        attr_name = 'scraper-fallback'
        count_attribute = 'scraper-fallback-counts'

    if attr_name not in tag.attrs:
        tag.attrs[attr_name] = '{}'

    tag_data = json.loads(tag.attrs[attr_name])

    if 'aggregate' in rule.get('tags'):
        label_regex = regex.compile('\\$[A-Z\\_]+\\$')
        found_labels = regex.findall(label_regex, data)

        for found_label in found_labels:
            formatted_label = found_label[1:-1].lower()
            value_text = tag_data[formatted_label]
            if len(value_text) > 0:
                data = data.replace(found_label, value_text)

    if 'prefix' in rule:
        data = rule['prefix'] + data

    tag_data[label] = data

    tag.attrs[attr_name] = json.dumps(tag_data)
    add_count_attribute(tag, label, count_attribute)


def add_count_attribute(tag, label, count_attribute):
    if count_attribute not in tag.attrs:
        tag.attrs[count_attribute] = '{}'

    tag_counts = json.loads(tag.attrs[count_attribute])

    if label not in tag_counts:
        tag_counts[label] = 1
    else:
        tag_counts[label] += 1

    tag.attrs[count_attribute] = json.dumps(tag_counts)
    if tag.parent is not None:
        add_count_attribute(tag.parent, label, count_attribute)


def use_fallback(soup):
    for tag in soup.find_all():
        if isinstance(tag, NavigableString):
            continue

        if 'scraper-fallback' in tag.attrs:
            data = {}
            if 'scraper-data' in tag.attrs:
                data = json.loads(tag.attrs['scraper-data'])

            data.update(json.loads(tag.attrs['scraper-fallback']))
            tag.attrs['scraper-data'] = json.dumps(data)

        if 'scraper-fallback-counts' in tag.attrs:
            counts = {}
            if 'scraper-counts' in tag.attrs:
                counts = json.loads(tag.attrs['scraper-counts'])

            counts.update(json.loads(tag.attrs['scraper-fallback-counts']))
            tag.attrs['scraper-counts'] = json.dumps(counts)

    return soup


def format_label(label):
    return f"${label.upper()}$"


def compile_regex(rule, input_regex):
    tags = rule.get('tags')

    if 'ignore_case' in tags:
        target_regex = regex.compile(input_regex, regex.IGNORECASE)
    else:
        target_regex = regex.compile(input_regex)

    return target_regex

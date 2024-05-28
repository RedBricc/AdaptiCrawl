import json
import logging
import traceback
from copy import copy

import regex
from bs4 import NavigableString

from scrapers.ScraperSettings import ScraperSettings
from services import SettingsService, TableCacheService

settings_service = SettingsService.service
TableCacheService = TableCacheService.service


def tag_values(soup, scraper_settings: ScraperSettings):
    soup = copy(soup)
    rules = settings_service.get_attribute_rules(scraper_settings.scraper_type)

    for rule in rules:
        tags = rule.get('tags')

        if 'labeled' in rule.get('tags'):
            example_replace_labeled(soup, rule, scraper_settings)

        # Can be both text and attribute
        if 'example_driven' in tags:
            if 'text' in tags:
                example_replace_text(soup, rule, scraper_settings)
            if 'attribute' in tags:
                example_replace_attributes(soup, rule, scraper_settings)
        if 'regex_driven' in tags:
            if 'text' in tags:
                regex_replace_text(soup, rule, scraper_settings)
            if 'attribute' in tags:
                regex_replace_attributes(soup, rule, scraper_settings)

    return soup


def example_replace_text(soup, rule, scraper_settings):
    label = rule.get('name')

    if 'table_sourced' in rule.get('tags'):
        table_name = rule.get('source')
        examples = TableCacheService.get_table_values(table_name)
    else:
        examples = rule.get('examples')

    if 'reorder_examples' in rule.get('tags'):
        examples = reorder_examples(examples)

    for example in examples:
        input_regex = f"\\b{regex.escape(str(example))}\\b"
        example_regex = compile_regex(rule, input_regex)
        found_tags = soup.find_all(string=example_regex)

        for tag in found_tags:
            if 'labeled' in rule.get('tags') and not has_label(rule, tag, example_regex, scraper_settings):
                continue

            if 'exclusive' in rule.get('tags'):
                label_regex = compile_regex(rule, f"\\b{regex.escape(label)}\\b")
                if regex.search(label_regex, tag):
                    continue

            filter_regex = None
            if 'filtered' in rule.get('tags'):
                filter_regex = compile_regex(rule, rule.get('filter_regex'))

            replace_text(example_regex, label, tag, filter_regex, rule)

    return soup


def has_label(rule, tag, value_regex, scraper_settings):
    max_label_distance = settings_service.get_scraper_setting('max_label_distance', scraper_settings.scraper_type)
    label = format_label(f"{rule.get('name')}_label")
    label_regex = regex.compile(".*" + regex.escape(label) + ".*")

    distance = 0
    target = get_tag(tag)

    while distance <= max_label_distance:
        found_labels = target.find_all(string=label_regex)
        for found_label in found_labels:
            try:
                if comes_after(target, found_label, label_regex, tag, value_regex):
                    return True
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.log(19, f"Exception while checking label distance in"
                                f"\n{tag.prettify()}"
                                f"\n{traceback.format_exc()}")

        if target.parent is None:
            return False

        target = target.parent
        distance += 1

    return False


def comes_after(parent, first_tag, first_regex, second_tag, second_regex):
    if first_tag == second_tag:
        first_pos = regex.search(first_regex, first_tag).start()
        second_pos = regex.search(second_regex, second_tag).start()

        return first_pos < second_pos

    tags = get_all_children(parent)
    for tag in tags:
        if tag == first_tag:
            return True
        if tag == second_tag:
            return False

        if isinstance(tag, NavigableString):
            continue
        tags.extend(list(tag.children))

    return False


def get_all_children(tag):
    tag = get_tag(tag)
    tags = [tag]
    for child in tag.children:
        if isinstance(child, NavigableString):
            if len(child.strip()) == 0:
                continue
            tags.append(child)
        else:
            tags.extend(get_all_children(child))
    return tags


def get_tag(tag):
    if isinstance(tag, NavigableString):
        return tag.parent
    return tag


def reorder_examples(examples):
    if examples is None:
        return []
    return sorted(examples, key=len, reverse=True)


def example_replace_labeled(soup, rule, scraper_settings):
    label_rule = {
        'name': f"{rule.get('name')}_label",
        'tags': ['example_driven'],
        'examples': rule.get('labels'),
    }

    if 'ignore_case' in rule.get('tags') or 'label_ignore_case' in rule.get('tags'):
        label_rule['tags'].append('ignore_case')
    if 'reorder_examples' in rule.get('tags'):
        label_rule['tags'].append('reorder_examples')

    if 'text' in rule.get('tags'):
        label_rule['tags'].append('text')
        example_replace_text(soup, label_rule, scraper_settings)

    if 'attribute' in rule.get('tags'):
        label_rule['tags'].append('attribute')
        example_replace_attributes(soup, label_rule, scraper_settings)


def regex_replace_text(soup, rule, scraper_settings):
    label = rule.get('name')

    input_regex = rule.get('regex')
    value_regex = compile_regex(rule, input_regex)
    found_tags = soup.find_all(string=value_regex)
    similar_examples = []

    for tag in found_tags:
        if 'labeled' in rule.get('tags') and not has_label(rule, tag, value_regex, scraper_settings):
            continue

        filter_regex = None
        if 'filtered' in rule.get('tags'):
            filter_regex = compile_regex(rule, rule.get('filter_regex'))

        examples = replace_text(value_regex, label, tag, filter_regex, rule)
        if 'replace_similar' in rule.get('tags'):
            similar_examples.append(examples)

    if 'replace_similar' in rule.get('tags'):
        similar_rule = format_similar_rule(rule, similar_examples)
        example_replace_text(soup, similar_rule, scraper_settings)

    return soup


def replace_text(target_regex, label, tag, filter_regex, rule):
    found = regex.search(target_regex, tag)
    found_text = found.group(0)

    if filter_regex is not None:
        found_text = filter_result(found_text, filter_regex)

    if len(found_text) == 0:
        return None

    formatted_label = format_label(label)
    tag_text = tag.string
    rez_text = "".join((tag_text[:found.start()], formatted_label, tag_text[found.start() + len(found_text):]))

    add_data_attribute(tag, label, found_text, rule)
    tag.replace_with(rez_text)

    return found_text


def example_replace_attributes(soup, rule, scraper_settings):
    label = rule.get('name')
    attribute_regex = regex.compile(rule.get('attribute_regex'))

    if 'table_sourced' in rule.get('tags'):
        table_name = rule.get('source')
        examples = TableCacheService.get_table_values(table_name)
    else:
        examples = rule.get('examples')

    if 'reorder_examples' in rule.get('tags'):
        examples = reorder_examples(examples)

    for example in examples:
        input_regex = f"\\b{regex.escape(example)}\\b"
        example_regex = compile_regex(rule, input_regex)

        filter_regex = None
        if 'filtered' in rule.get('tags'):
            filter_regex = compile_regex(rule, rule.get('filter_regex'))

        replace_attributes(soup, attribute_regex, example_regex, label, filter_regex, rule, scraper_settings)

    return soup


def regex_replace_attributes(soup, rule, scraper_settings):
    label = rule.get('name')
    attribute_regex = regex.compile(rule.get('attribute_regex'))

    input_regex = rule.get('regex')
    value_regex = compile_regex(rule, input_regex)

    filter_regex = None
    if 'filtered' in rule.get('tags'):
        filter_regex = compile_regex(rule, rule.get('filter_regex'))

    similar_examples = replace_attributes(soup, attribute_regex, value_regex, label, filter_regex, rule,
                                          scraper_settings)

    if 'replace_similar' in rule.get('tags'):
        similar_rule = format_similar_rule(rule, similar_examples)
        example_replace_attributes(soup, similar_rule, scraper_settings)

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


def replace_attributes(soup, attribute_regex, target_regex, label, filter_regex, rule, scraper_settings):
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
                    if 'labeled' in rule.get('tags') and not has_label(rule, tag, target_regex, scraper_settings):
                        continue

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
            value_texts = tag_data[formatted_label]
            for value_text in value_texts:
                if len(value_text) > 0:
                    data = data.replace(found_label, value_text)

    if 'prefix' in rule:
        data = rule['prefix'] + data

    if label not in tag_data:
        tag_data[label] = [data]
    else:
        tag_data[label].append(data)

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


def format_label(label):
    return f"${label.upper()}$"


def compile_regex(rule, input_regex):
    tags = rule.get('tags')

    if 'ignore_case' in tags:
        target_regex = regex.compile(input_regex, regex.IGNORECASE)
    else:
        target_regex = regex.compile(input_regex)

    return target_regex

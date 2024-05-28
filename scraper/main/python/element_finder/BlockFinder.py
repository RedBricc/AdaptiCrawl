import json
import logging
import timeit

from bs4 import NavigableString

from element_finder import AttributeParser
from services import SettingsService

settings_service = SettingsService.service


def find_new_blocks(soup, driver, scraper_settings, records_with_images=None, default_images=None, records=None):
    if records is None:
        records = {}

    found_blocks = find_blocks(soup, driver, scraper_settings, records_with_images, default_images)
    unique_blocks = merge_duplicates(found_blocks)

    largest_group = get_largest_group(unique_blocks, scraper_settings)
    new_blocks = get_new_blocks(largest_group, records)

    return new_blocks


def find_blocks(soup, driver, scraper_settings, records_with_images=None,
                default_images=None, record_alias=None, prioritize_first=False):
    if records_with_images is None:
        records_with_images = []
    if default_images is None:
        default_images = []

    required_attributes = get_required_attributes(scraper_settings)

    remove_untagged(soup)
    blocks = soup_to_blocks(soup, required_attributes)
    moved_blocks = move_up_blocks(blocks, required_attributes)

    if prioritize_first is True and len(moved_blocks) > 0:
        moved_blocks = add_all_non_block_children(moved_blocks[0], moved_blocks)

    culled_blocks = cull_blocks(moved_blocks, scraper_settings)
    parsed_blocks = parse_blocks(culled_blocks, driver, scraper_settings, records_with_images, default_images,
                                 record_alias)

    return parsed_blocks


def remove_untagged(soup):
    start = timeit.default_timer()
    for tag in soup.find_all():
        if 'scraper-counts' not in tag.attrs and 'scraper-fallback-counts' not in tag.attrs:
            tag.extract()

    logging.log(19, f"BlockFinder > Remove untagged {timeit.default_timer() - start:.3f}s")

    return soup


def soup_to_blocks(soup, required_attributes):
    start = timeit.default_timer()

    blocks = []
    tags = [soup]

    while len(tags) > 0:
        tag = tags.pop(0)

        is_block = True
        for child in tag.children:
            if has_required_attributes(child, required_attributes):
                tags.append(child)
                is_block = False

        if is_block:
            blocks.append(tag)

    logging.log(19, f"BlockFinder > Soup to blocks {timeit.default_timer() - start:.3f}s")

    return blocks


def has_required_attributes(tag, required_attributes):
    if isinstance(tag, NavigableString):
        return False

    tag_counts = json.loads(tag.attrs.get('scraper-counts', '{}'))
    tag_counts.update(json.loads(tag.attrs.get('scraper-fallback-counts', '{}')))

    for required_attribute in required_attributes:
        if required_attribute in tag_counts:
            continue

        return False

    return True


def has_anti_attributes(tag, anti_attributes):
    if isinstance(tag, NavigableString):
        return False

    tag_counts = json.loads(tag.attrs.get('scraper-counts', '{}'))

    for anti_attribute in anti_attributes:
        if anti_attribute in tag_counts:
            return True

    return False


def get_required_attributes(scraper_settings):
    start = timeit.default_timer()

    attribute_rules = settings_service.get_attribute_rules(scraper_settings.scraper_type)
    required_attributes = []

    for rule in attribute_rules:
        if rule.get('required') is True:
            required_attributes.append(rule['name'])

    logging.log(19, f"BlockFinder > Get required attributes {timeit.default_timer() - start:.3f}s")

    return required_attributes


def get_anti_attributes(scraper_settings):
    start = timeit.default_timer()

    attribute_rules = settings_service.get_attribute_rules(scraper_settings.scraper_type)
    anti_attributes = []

    for rule in attribute_rules:
        if 'anti_attribute' in rule['tags']:
            anti_attributes.append(rule['name'])

    logging.log(19, f"BlockFinder > Get anti-attributes {timeit.default_timer() - start:.3f}s")

    return anti_attributes


def move_up_blocks(blocks, required_attributes):
    start = timeit.default_timer()

    if len(blocks) == 1:
        return blocks

    moved_blocks = []

    for block in blocks:
        moved_block = move_up_block(block, required_attributes)
        moved_blocks.append(moved_block)

    logging.log(19, f"BlockFinder > Move up blocks {timeit.default_timer() - start:.3f}s")

    return moved_blocks


def move_up_block(block, required_attributes):
    while block.parent is not None:
        if block.name == 'body':
            return block
        if len(list(block.parent.children)) == 1:
            block = block.parent
            continue
        for child in block.parent.children:
            if child == block:
                continue
            if not has_required_attributes(child, required_attributes):
                continue
            if get_alias(child) is not None and get_alias(child) != get_alias(block):
                return block

        block = block.parent
    return block


def get_alias(tag):
    aliases = find_attribute_values(tag, 'alias')
    if len(aliases) == 0:
        return None
    return aliases[0]


def cull_blocks(blocks, scraper_settings):
    start = timeit.default_timer()
    anti_attributes = get_anti_attributes(scraper_settings)

    culled_blocks = []
    for block in blocks:
        if not has_anti_attributes(block, anti_attributes):
            culled_blocks.append(block)

    logging.log(19, f"BlockFinder > Cull blocks {timeit.default_timer() - start:.3f}s")

    return culled_blocks


def parse_blocks(blocks, driver, scraper_settings, records_with_images, default_images, record_alias):
    start = timeit.default_timer()

    parsed_blocks = []

    for block in blocks:
        parsed_block = parse_block(block, driver, scraper_settings, records_with_images, default_images, record_alias)
        if parsed_block is not None:
            parsed_blocks.append(parsed_block)

    logging.log(19, f"BlockFinder > Parse blocks {timeit.default_timer() - start:.3f}s")

    return parsed_blocks


def merge_duplicates(parsed_blocks):
    start = timeit.default_timer()

    unique_blocks = []
    unique_aliases = set()

    for block in parsed_blocks:
        alias = block['alias']
        if alias not in unique_aliases:
            unique_blocks.append(block)
            unique_aliases.add(alias)

    logging.log(19, f"BlockFinder > Merge duplicates {timeit.default_timer() - start:.3f}s")

    return unique_blocks


def get_new_blocks(parsed_blocks, records):
    start = timeit.default_timer()

    new_blocks = []

    for block in parsed_blocks:
        alias = block['alias']
        if alias not in records:
            new_blocks.append(block)

    logging.log(19, f"BlockFinder > Get new blocks {timeit.default_timer() - start:.3f}s")

    return new_blocks


def parse_block(block, driver, scraper_settings, records_with_images, default_images, record_alias):
    attribute_rules = settings_service.get_attribute_rules(scraper_settings.scraper_type)
    hash_record_images = settings_service.get_scraper_setting('hash_record_images', scraper_settings.scraper_type)

    parsed_block = {}

    for attribute in attribute_rules:
        name = attribute.get('name')
        values = find_attribute_values(block, name)

        if values is None or len(values) == 0:
            parsed_block[name] = attribute.get('default')
            continue

        if name == 'record_image':
            record_alias = record_alias or parsed_block['alias']
            if hash_record_images is True and record_alias not in records_with_images:
                parsed_value = AttributeParser.parse_attribute(attribute, values, driver, default_images)
                parsed_block[name] = parsed_value
            continue

        parsed_value = AttributeParser.parse_attribute(attribute, values)
        parsed_block[name] = parsed_value

    parsed_block['tag'] = block
    parsed_block['index'] = block.attrs['scraper-index']

    return parsed_block


def find_attribute_values(tag, name):
    tags = [tag]
    tags.extend(tag.find_all())

    found_values = find_values(tags, name, 'scraper-data')

    if len(found_values) > 0:
        return found_values

    return find_values(tags, name, 'scraper-fallback')


def find_values(tags, name, data_attribute):
    found_values = []

    for tag in tags:
        if tag.attrs is not None and data_attribute in tag.attrs:
            data = json.loads(tag.attrs[data_attribute])
            if name in data:
                found_values.extend(data[name])

    return found_values


def get_xpath(tag):
    xpath = ''
    while tag.parent is not None:
        tag_number = 1
        tag_count = 0

        if tag.parent is not None:
            for sibling in tag.parent.children:
                if sibling.name == tag.name:
                    tag_count += 1
                    if sibling == tag:
                        tag_number = tag_count

        tag_index_string = ''
        if tag_count > 1:
            tag_index_string = f"[{tag_number}]"

        xpath = '/' + tag.name + tag_index_string + xpath
        tag = tag.parent

    return xpath


def get_largest_group(blocks, scraper_settings):
    if len(blocks) == 0:
        return []

    start = timeit.default_timer()

    max_tag_distance = settings_service.get_scraper_setting('max_tag_distance', scraper_settings.scraper_type)
    groups = []

    for block in blocks:
        if 'group_id' in block:
            continue

        group = []

        for other_block in blocks:
            distance = get_distance(block['tag'], other_block['tag'])
            if distance <= max_tag_distance:
                other_block['group_id'] = len(groups)
                group.append(other_block)

        groups.append(group)

    longest_group = []
    for group in groups:
        if len(group) > len(longest_group):
            longest_group = group

    block_parent = find_parent_block(longest_group)
    for block in longest_group:
        block['parent'] = block_parent.attrs['scraper-index']

    logging.log(19, f"BlockFinder > Get largest group {timeit.default_timer() - start:.3f}s")

    return longest_group


def get_distance(tag, other_tag):
    block_xpath = get_xpath(tag)[1:].split('/')
    other_block_xpath = get_xpath(other_tag)[1:].split('/')

    block_length = len(block_xpath)
    other_block_length = len(other_block_xpath)

    tag_index = 0
    for tag_index in range(min(block_length, other_block_length)):
        if block_xpath[tag_index] != other_block_xpath[tag_index]:
            break

    block_distance = block_length - tag_index - 1
    other_block_distance = other_block_length - tag_index - 1

    distance = block_distance + other_block_distance + 1

    if distance == 1 and block_xpath[tag_index] == other_block_xpath[tag_index]:
        distance = 0  # same tag

    return distance


def find_parent_block(blocks):
    parent_block = blocks[0]['tag'].parent
    found_parent = False
    while found_parent is False and parent_block is not None:
        found_parent = True
        for block in blocks:
            tag = block['tag']
            if not is_parent(tag, parent_block):
                parent_block = parent_block.parent
                found_parent = False
                break

    if parent_block is None:
        logging.warning(f"Could not find parent block!")
        return blocks[0]['tag']

    return parent_block


def is_parent(tag, parent):
    while tag.parent is not None:
        if tag.parent == parent:
            return True
        tag = tag.parent
    return False


def add_all_non_block_children(block, record_blocks):
    parent = block.parent
    if parent is None:
        return record_blocks

    children = parent.find_all(recursive=False)

    non_block_tags = []
    for child in children:
        if child not in record_blocks:
            non_block_tags.append(child)

    for tag in non_block_tags:
        block.append(tag)

        tag_scraper_counts = json.loads(tag.attrs.get('scraper-counts', '{}'))
        block_scraper_counts = json.loads(block.attrs.get('scraper-counts', '{}'))

        for scraper_count in tag_scraper_counts:
            if scraper_count not in block_scraper_counts:
                block_scraper_counts[scraper_count] = tag_scraper_counts[scraper_count]
            else:
                block_scraper_counts[scraper_count] += tag_scraper_counts[scraper_count]

        block.attrs['scraper-counts'] = json.dumps(block_scraper_counts)

        tag_scraper_fallback_counts = json.loads(tag.attrs.get('scraper-fallback-counts', '{}'))
        block_scraper_fallback_counts = json.loads(block.attrs.get('scraper-fallback-counts', '{}'))

        for scraper_fallback_count in tag_scraper_fallback_counts:
            if scraper_fallback_count not in block_scraper_fallback_counts:
                block_scraper_fallback_counts[scraper_fallback_count] = tag_scraper_fallback_counts[scraper_fallback_count]
            else:
                block_scraper_fallback_counts[scraper_fallback_count] += tag_scraper_fallback_counts[scraper_fallback_count]

        block.attrs['scraper-fallback-counts'] = json.dumps(block_scraper_fallback_counts)

    return record_blocks

import json
import logging
import random
import time

from bs4 import NavigableString

from element_finder import AttributeParser
from preprocessing import ValueTagger
from services import SettingsService

SettingsService = SettingsService.service


def find_blocks(soup, fallback=False):
    if fallback is True:
        soup = ValueTagger.use_fallback(soup)

    required_attributes = get_required_attributes()

    remove_untagged(soup)
    blocks = soup_to_blocks(soup, required_attributes)
    moved_blocks = move_up_blocks(blocks, required_attributes)

    parsed_blocks = parse_blocks(moved_blocks, fallback)

    if len(parsed_blocks) == 0:
        return []

    largest_group = get_largest_group(parsed_blocks)

    return largest_group


def remove_untagged(soup):
    for tag in soup.find_all():
        if 'scraper-counts' not in tag.attrs and 'scraper-fallback-counts' not in tag.attrs:
            tag.extract()

    return soup


def soup_to_blocks(soup, required_attributes):
    blocks = []
    tags = [soup]

    while len(tags) > 0:
        tag = tags.pop(0)

        is_block = True
        for child in tag.children:
            if has_all_required_attributes(child, required_attributes):
                tags.append(child)
                is_block = False

        if is_block:
            blocks.append(tag)

    return blocks


def has_all_required_attributes(tag, required_attributes):
    if isinstance(tag, NavigableString):
        return False

    tag_counts = json.loads(tag.attrs.get('scraper-counts', '{}'))

    for required_attribute in required_attributes:
        if required_attribute not in tag_counts:
            return False

    return True


def get_required_attributes():
    attribute_rules = SettingsService.get_catalog_setting('attribute_rules')
    required_attributes = []

    for rule in attribute_rules:
        if rule.get('required') is True:
            required_attributes.append(rule['name'])

    return required_attributes


def move_up_blocks(blocks, required_attributes):
    if len(blocks) == 1:
        return blocks

    moved_blocks = []

    for block in blocks:
        moved_block = move_up_block(block, required_attributes)
        moved_blocks.append(moved_block)

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
            if has_all_required_attributes(child, required_attributes):
                return block

        block = block.parent
    return block


def parse_blocks(blocks, strict):
    parsed_blocks = []
    for block in blocks:
        parsed_block = parse_block(block, strict)
        if parsed_block is not None:
            parsed_blocks.append(parsed_block)

    return parsed_blocks


def parse_block(block, strict):
    attribute_rules = SettingsService.get_catalog_setting('attribute_rules')
    parsed_block = {}

    for attribute in attribute_rules:
        name = attribute.get('name')
        value = find_attribute(block, attribute)
        if value is None:
            if attribute.get('required') is True:
                if strict is True:
                    logging.warning(f"Required attribute {name} not found in block!")
                    return None
            parsed_block[name] = attribute.get('default')
            continue

        parsed_value = AttributeParser.parse_attribute(attribute, value)
        parsed_block[name] = parsed_value

    parsed_block['tag'] = block
    parsed_block['index'] = block.attrs['scraper-index']

    return parsed_block


def find_attribute(tag, attribute):
    name = attribute.get('name')

    if 'scraper-data' not in tag.attrs:
        return find_attribute_in_children(tag, attribute)

    data = json.loads(tag.attrs['scraper-data'])
    if name in data:
        return data[name]

    return find_attribute_in_children(tag, attribute)


def find_attribute_in_children(tag, attribute):
    for child in tag.children:
        if isinstance(child, NavigableString):
            continue

        found_value = find_attribute(child, attribute)
        if found_value is not None:
            return found_value

    return None


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


def get_largest_group(blocks):
    degrees_of_separation = SettingsService.get_catalog_setting('max_tag_distance')
    groups = []

    for block in blocks:
        if 'group_id' in block:
            continue

        group = []

        for other_block in blocks:
            distance = get_distance(block['tag'], other_block['tag'])
            if distance <= degrees_of_separation:
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

    distance = block_distance + other_block_distance

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
        logging.warning(f"Could not find parent block for {blocks}!")
        return blocks[0]['tag']

    return parent_block


def is_parent(tag, parent):
    while tag.parent is not None:
        if tag.parent == parent:
            return True
        tag = tag.parent
    return False

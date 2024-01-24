import regex
from services import SettingsService

SettingsService = SettingsService.service


def parse_attribute(attribute, value):
    attribute_type = SettingsService.get_group_setting(attribute, 'type')
    
    if attribute_type == 'text':
        return value
    elif attribute_type == 'float':
        return convert_value(attribute, value)
    elif attribute_type == 'int':
        converted_value = convert_value(attribute, value)
        return int(converted_value)
    else:
        return None


def convert_value(attribute, value):
    conversions = attribute.get('conversions')

    if conversions is None:
        return get_float(value)

    found_multiplier = 1
    for conversion in conversions:
        conversion_regex = SettingsService.get_group_setting(conversion, 'regex')
        conversion_multiplier = SettingsService.get_group_setting(conversion, 'multiplier')

        found_value = regex.search(conversion_regex, value)
        if found_value is not None:
            found_multiplier = conversion_multiplier
            break

    return get_float(value) * found_multiplier


def get_float(string):
    replaced_trailing_comma = regex.sub(',(?=\\d{1,2}\\b)', '.', string)
    replaced_delimiter_commas = regex.sub(',(?=\\d{3})', '', replaced_trailing_comma)
    replaced_non_numbers = regex.sub('[^\\d\\.]', '', replaced_delimiter_commas)

    return float(replaced_non_numbers)

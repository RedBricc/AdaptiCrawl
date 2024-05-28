import logging
import traceback

import regex
import requests
import urllib3

from services import SettingsService
from services.ImageService import RecordImage

settings_service = SettingsService.service


def parse_attribute(attribute, values, driver=None, default_images=None):
    """
    Given potential values, parse the best value for the attribute.
    :param attribute: Attribute rule
    :param values: List of potential values
    :param driver: Selenium driver
    :param default_images: List of default images
    :return: The best value for the given attribute
    """

    attribute_type = attribute.get('type')

    if values is None or len(values) == 0:
        return None

    if attribute_type == 'text':
        value = values[0]

        if attribute.get('tags') is None:
            return value

        if 'translated' in attribute.get('tags'):
            translations = attribute.get('translations') or {}

            if 'ignore_case' in attribute.get('tags'):
                value = value.lower()
                translations = {k.lower(): v for k, v in translations.items()}

            if value in translations:
                return translations[value]

        return value
    elif attribute_type == 'float':
        return get_numeric_value(attribute, values)
    elif attribute_type == 'int':
        return int(get_numeric_value(attribute, values))
    elif attribute_type == 'link':
        return values[0]
    elif attribute_type == 'date':
        return get_date(values[0])
    elif attribute_type == 'image_link':
        return get_image(values, driver, default_images)
    else:
        return None


def get_numeric_value(attribute, values):
    """
    :return: The best value for the given attribute, depending on the attribute's constraints.
             If no constraints are set, the first value is returned.
    """

    converted_values = convert_values(attribute, values)
    final_value = apply_constraints(converted_values, attribute)

    return final_value


def convert_values(attribute, values):
    """
    Convert the given values to floats, and apply any conversions
    :param attribute: The attribute rule
    :param values: List of values to convert
    :return: The converted values
    """
    tags = attribute.get('tags')

    case_sensitive = True
    if tags is not None:
        case_sensitive = 'ignore_case' not in tags

    conversions = attribute.get('conversions')
    converted_values = []

    for value in values:
        converted_values.append(convert_value(conversions, value, case_sensitive))

    return converted_values


def convert_value(conversions, value, case_sensitive=True):
    found_multiplier = 1

    if conversions is not None:
        for conversion in conversions:
            conversion_regex = conversion.get('regex')
            if case_sensitive is False:
                conversion_regex = regex.compile(conversion_regex, regex.IGNORECASE)

            conversion_multiplier = conversion.get('multiplier')

            found_value = regex.search(conversion_regex, value)
            if found_value is not None:
                found_multiplier = conversion_multiplier
                break

    return get_float(value) * found_multiplier


def apply_constraints(values, attribute):
    constraints = attribute.get('constraints')

    final_value = values[0]

    if constraints is None:
        return final_value

    sorted_values = sorted(values, reverse=True)

    if 'discard_smaller_than' in constraints:
        discard_smaller_than = constraints['discard_smaller_than']

        if discard_smaller_than.endswith('%'):
            percent_value = float(discard_smaller_than[:-1])
            discard_smaller_than = sorted_values[0] * (percent_value / 100)
        else:
            discard_smaller_than = float(discard_smaller_than)

        for value in sorted_values.copy():
            if value < discard_smaller_than:
                sorted_values.remove(value)

        final_value = sorted_values[0]

    if 'prioritize_nth_biggest' in constraints:
        prioritize_nth_biggest = constraints['prioritize_nth_biggest']
        if len(sorted_values) >= prioritize_nth_biggest:
            final_value = sorted_values[prioritize_nth_biggest - 1]

    return final_value


def get_float(string):
    replaced_trailing_comma = regex.sub(',(?=\\d{1,2}\\b)', '.', string)
    replaced_delimiter = regex.sub('[,\\.](?=\\d{3})', '', replaced_trailing_comma)
    replaced_non_numbers = regex.sub('[^\\d\\.]', '', replaced_delimiter)

    return float(replaced_non_numbers)


def get_date(string):
    if string is None:
        return None

    string = regex.sub(r'[\s,/\\]', '.', string)

    year_regex = regex.compile('\\d{4}$|^\\d{4}')
    year = regex.search(year_regex, string)
    if year is None:
        return None

    final_date = year.group(0)

    day_month = regex.sub(year_regex, 'y', string)

    month_regex = regex.compile('\\d{1,2}\\.y$|^y\\.\\d{1,2}')
    month = regex.search(month_regex, day_month)

    if month is None:
        return f'{final_date}-01-01'

    final_month = regex.sub('.?y.?', '', month.group(0))

    final_date = f"{final_date}-{final_month}"

    day = regex.sub(regex.escape(month.group(0)), '', day_month)
    day = regex.search(r'^\d{1,2}', day)

    if day is None:
        return f'{final_date}-01'

    return f"{final_date}-{day.group(0)}"


def get_image(links, driver, default_images):
    """
    Get the record image from the given links
    :return: First record image found
    """

    if driver is None:
        return None

    for image_link in links:
        if image_link is None:
            continue

        record_image = get_record_image(image_link, driver)

        if record_image is None:
            continue

        if record_image.hash in default_images:
            return None

        return record_image

    return None


def get_record_image(image_link, driver):
    """
    Download the record image if possible
    :param image_link: The image link
    :param driver: The driver to use
    :return: The formatted image
    """
    try:
        with requests.Session() as session:
            urllib3.disable_warnings()
            session.verify = False

            selenium_user_agent = driver.execute_script("return navigator.userAgent;")
            session.headers.update({"user-agent": selenium_user_agent})

            for cookie in driver.get_cookies():
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

            if not image_link.startswith('http'):
                return None

            try:
                response = session.request("GET", image_link, stream=True)
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.warning(f"Failed to download image: {image_link}!\n{traceback.format_exc()}")
                return None

            if not response.ok:
                return None

            try:
                image_extension = response.headers['Content-Type'].split('/')[1]
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                image_extension = image_link.split('.')[-1]

            try:
                return RecordImage(image_link,
                                    image_extension,
                                    response.content)
            except SystemExit or KeyboardInterrupt:
                exit(-1)
            except:
                logging.error(f"Failed to create record image: {image_link}!\n{traceback.format_exc()}")
                return None
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to download image: {image_link}!\n{traceback.format_exc()}")
        return None

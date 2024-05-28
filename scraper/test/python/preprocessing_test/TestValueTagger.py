import unittest

import regex
from bs4 import BeautifulSoup

from scrapers.ScraperSettings import ScraperSettings
from services import SettingsService
from preprocessing import ValueTagger

settings_service = SettingsService.service
input_html = ('<html><body><div>'
              '<a href="replace.com"><span>Label REPLACE ME goes here</span></a>'
              '<a href="https:replace.com/"><span>Label REPLACE ME goes here</span></a>'
              '<a href="REPLACE.COM"><span>Second label replace me goes here</span></a>'
              '<a href="keep.org"><span>Ignore this REPLACE seperated ME request</span></a>'
              '</div></body></html>')


class ValueTaggerTest(unittest.TestCase):

    def test_example_replace_text_strict(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": ".*",
            "tags": [
                "text",
                "example_driven"
            ],
            "examples": [
                "REPLACE ME"
            ]
        }

        ValueTagger.example_replace_text(soup, rule, ScraperSettings())

        self.check_text_strict(soup)

    def test_example_replace_text_ignore_case(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": ".*",
            "tags": [
                "text",
                "example_driven",
                "ignore_case"
            ],
            "examples": [
                "REPLACE ME"
            ]
        }

        ValueTagger.example_replace_text(soup, rule, ScraperSettings())

        self.check_text_ignore_case(soup)

    def test_example_replace_attributes_strict(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": ".*",
            "tags": [
                "attribute",
                "example_driven"
            ],
            "attribute_regex": "\\bhref$",
            "examples": [
                "replace.com"
            ]
        }

        ValueTagger.example_replace_attributes(soup, rule, ScraperSettings())

        self.check_attributes_strict(soup)

    def test_example_replace_attributes_ignore_case(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": ".*",
            "tags": [
                "attribute",
                "example_driven",
                "ignore_case"
            ],
            "attribute_regex": "\\bhref$",
            "examples": [
                "replace.com"
            ]
        }

        ValueTagger.example_replace_attributes(soup, rule, ScraperSettings())

        self.check_attributes_ignore_case(soup)

    def test_regex_replace_text_strict(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "REPLACE ME",
            "tags": [
                "text",
                "regex_driven"
            ],
            "examples": [
                "goes here"
            ]
        }

        ValueTagger.regex_replace_text(soup, rule, ScraperSettings())

        self.check_text_strict(soup)

    def test_regex_replace_text_ignore_case(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "REPLACE ME",
            "tags": [
                "text",
                "regex_driven",
                "ignore_case"
            ],
            "examples": [
                "goes here"
            ]
        }

        ValueTagger.regex_replace_text(soup, rule, ScraperSettings())

        self.check_text_ignore_case(soup)

    def test_regex_replace_attributes(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "\\S*\\.com",
            "tags": [
                "attribute",
                "regex_driven"
            ],
            "attribute_regex": "\\bhref$",
            "examples": [
                "goes here"
            ]
        }

        ValueTagger.regex_replace_attributes(soup, rule, ScraperSettings())

        self.check_attributes_strict(soup)

    def test_regex_replace_attributes_ignore_case(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "\\S*\\.com",
            "tags": [
                "attribute",
                "regex_driven",
                "ignore_case"
            ],
            "attribute_regex": "\\bhref$",
            "examples": [
                "goes here"
            ]
        }

        ValueTagger.regex_replace_attributes(soup, rule, ScraperSettings())

        self.check_attributes_ignore_case(soup)

    def test_replace_similar(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "(?<=REPLACE\\s)ME",
            "tags": [
                "text",
                "regex_driven",
                "replace_similar"
            ],
            "examples": [
                "goes here"
            ]
        }

        ValueTagger.regex_replace_text(soup, rule, ScraperSettings())

        self.assertIsNotNone(soup.find(string='Ignore this REPLACE seperated $TEST$ request')
                             , f'Similar values was not replaced {soup.prettify()}')

    def test_filter_result(self):
        test_data = [
            'Remove everything after THIS',
            'Remove everything after THIS part',
            'Remove everything after'
        ]
        filter_regex = regex.compile('THIS')

        expected_result = 'Remove everything after'

        for test in test_data:
            filtered_result = ValueTagger.filter_result(test, filter_regex)
            self.assertEqual(expected_result, filtered_result,
                             'Filtering did not work as expected')

    def test_replace_with_filter(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        rule = {
            "name": "test",
            "regex": "REPLACE",
            "tags": [
                "text",
                "attribute",
                "regex_driven",
                "filtered"
            ],
            "attribute_regex": "\\bhref$",
            "filter_regex": "PLACE"
        }

        ValueTagger.regex_replace_text(soup, rule, ScraperSettings())
        ValueTagger.regex_replace_attributes(soup, rule, ScraperSettings())

        self.assertEqual(2, len(soup.findAll(string='Label $TEST$PLACE ME goes here')),
                         f'Value was replaced incorrectly in text {soup.prettify()}')
        self.assertNotEqual([], soup.find_all(attrs={"href": "$TEST$PLACE.COM"}),
                            f'Value was replaced incorrectly in attribute {soup.prettify()}')

    def test_replace_instances_chained(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = [
            {
                "name": "test",
                "regex": "Label",
                "tags": [
                    "text",
                    "example_driven"
                ],
                "examples": [
                    "REPLACE"
                ]
            },
            {
                "name": "test2",
                "regex": "(?<=\\$TEST\\$\\s)ME",
                "tags": [
                    "text",
                    "regex_driven"
                ],
                "examples": [
                    "here"
                ]
            },
            {
                "name": "test3",
                "regex": "(?<=\\$TEST2\\$\\s)GOeS",
                "tags": [
                    "text",
                    "regex_driven",
                    "ignore_case"
                ],
                "examples": [
                    "$TEST2$ goes"
                ]
            }
        ]
        settings_service.mock_attribute_settings(settings)

        soup = ValueTagger.tag_values(soup, ScraperSettings())

        self.assertEqual([], soup.findAll(string=regex.compile(".*REPLACE.*")),
                         f'fExample value was not replaced {soup.prettify()}')
        self.assertEqual(['Ignore this $TEST$ seperated ME request'], soup.findAll(string=regex.compile(".*ME.*")),
                         f'Regex strict text value was not replaced {soup.prettify()}')
        self.assertEqual(['Second label replace me goes here'], soup.findAll(string=regex.compile(".*goes.*")),
                         f'Regex ignore case text value was not replaced {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Label $TEST$ $TEST2$ $TEST3$ here'),
                             f'Not all values were replaced {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Second label replace me goes here'),
                             f'Value was replaced out of chain {soup.prettify()}')

    def test_replace_multiple(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = [
            {
                "name": "test",
                "tags": [
                    "text",
                    "example_driven"
                ],
                "examples": [
                    "REPLACE",
                    "ME"
                ]
            }
        ]
        settings_service.mock_attribute_settings(settings)

        soup = ValueTagger.tag_values(soup, ScraperSettings())

        self.assertEqual([], soup.findAll(string=regex.compile(".*REPLACE.*")),
                         f'Example value was not replaced {soup.prettify()}')
        self.assertEqual([], soup.findAll(string=regex.compile(".*ME.*")),
                         f'Regex strict text value was not replaced {soup.prettify()}')

        self.assertEqual('{"test": ["REPLACE", "ME"]}', soup.find('span').attrs['scraper-data'],
                         f'Attribute was not replaced {soup.prettify()}')

    def check_text_strict(self, soup):
        self.assertEqual([], soup.findAll(string=regex.compile(".*REPLACE ME.*")),
                         f'Value was not replaced {soup.prettify()}')
        self.assertIsNone(soup.find(string='Second label $TEST$ goes here'),
                          f'Value (ignore case) was replaced with correct label {soup.prettify()}')

        self.assertIsNotNone(soup.findAll(string=regex.compile(".*replace me.*")),
                             f'Value (ignore case) was replaced {soup.prettify()}')
        self.assertIsNotNone(soup.findAll(string=regex.compile(".*\\$TEST\\$.*")),
                             f'No label was added {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Label $TEST$ goes here'),
                             f'Value was not replaced with correct label {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Ignore this REPLACE seperated ME request'),
                             f'Value was replaced incorrectly {soup.prettify()}')

    def check_text_ignore_case(self, soup):
        self.assertIsNone(soup.find('REPLACE ME'),
                          f'Value was not replaced {soup.prettify()}')
        self.assertIsNone(soup.find('replace me'),
                          f'Value (ignore case) was not replaced {soup.prettify()}')

        self.assertIsNotNone(soup.findAll(string=regex.compile(".*\\$TEST\\$.*")),
                             f'No label was added {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Label $TEST$ goes here'),
                             f'Value was not replaced with correct label {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Second label $TEST$ goes here'),
                             f'Value (ignore case) was not replaced with correct label {soup.prettify()}')
        self.assertIsNotNone(soup.find(string='Ignore this REPLACE seperated ME request'),
                             f'Value was replaced incorrectly {soup.prettify()}')

    def check_attributes_strict(self, soup):
        self.assertEqual([], soup.find_all(attrs={"href": "replace.com"}),
                         f'Attribute was not replaced {soup.prettify()}')
        self.assertEqual([], soup.find_all(attrs={"href": "replace.com"}),
                         f'Attribute with additional characters was not replaced {soup.prettify()}')
        self.assertNotEqual([], soup.find_all(attrs={"href": "REPLACE.COM"}),
                            f'Attribute (ignore case) was replaced {soup.prettify()}')
        self.assertNotEqual([], soup.find_all(attrs={"href": "keep.org"}),
                            f'Non-matching attribute was replaced {soup.prettify()}')

    def check_attributes_ignore_case(self, soup):
        self.assertEqual([], soup.find_all(attrs={"href": "replace.com"}),
                         f'Attribute was not replaced {soup.prettify()}')
        self.assertEqual([], soup.find_all(attrs={"href": "replace.com"}),
                         f'Attribute with additional characters was not replaced {soup.prettify()}')
        self.assertEqual([], soup.find_all(attrs={"href": "REPLACE.COM"}),
                         f'Attribute (ignore case) was not replaced {soup.prettify()}')
        self.assertNotEqual([], soup.find_all(attrs={"href": "keep.org"}),
                            f'Non-matching attribute was replaced {soup.prettify()}')


if __name__ == '__main__':
    unittest.main()

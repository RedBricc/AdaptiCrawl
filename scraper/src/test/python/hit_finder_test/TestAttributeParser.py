import unittest

from element_finder import AttributeParser

input_strings = ['3,950 €', '2,470€', '12 700 €', '€26,950.00', '€1,250,950.00', '€23 500', '137 km', '100,7 km',
                 '2132km', '12thd', '120 thd', '15.6thd', '16.6 thd']


class RecordParserTest(unittest.TestCase):
    def test_parse_float(self):
        expected_results = [3950.0, 2470.0, 12700.0, 26950.0, 1250950.0, 23500.0, 137.0, 100.7,
                            2132.0, 12.0, 120.0, 15.6, 16.6]

        for i in range(len(input_strings)):
            self.assertEqual(expected_results[i], AttributeParser.get_float(input_strings[i]),
                             f"Float was not parsed correctly for input string: {input_strings[i]}")

    def test_convert_value(self):
        expected_results = [3950.0, 2470.0, 12700.0, 26950.0, 1250950.0, 23500.0, 137.0, 100.7,
                            2132.0, 12000.0, 120000.0, 15600.0, 16600.0]
        attribute = {
            'type': 'float',
            'conversions': [{'regex': 'thd', 'multiplier': 1000}]
        }

        for i in range(len(input_strings)):
            self.assertEqual(expected_results[i], AttributeParser.parse_attribute(attribute, input_strings[i]),
                             f"Value was not converted correctly for input string: {input_strings[i]}")

    def test_parse_attribute(self):
        expected_float_results = [3950.0, 2470.0, 12700.0, 26950.0, 1250950.0, 23500.0, 137.0, 100.7,
                                  2132.0, 12000.0, 120000.0, 15600.0, 16600.0]
        expected_int_results = [3950, 2470, 12700, 26950, 1250950, 23500, 137, 100, 2132, 12000, 120000, 15600, 16600]
        expected_text_results = input_strings

        attributes = {
            "attribute_rules": [
                {
                    'type': 'float',
                    'conversions': [{'regex': 'thd', 'multiplier': 1000}]
                },
                {
                    'type': 'int',
                    'conversions': [{'regex': 'thd', 'multiplier': 1000}]
                },
                {
                    'type': 'text'
                }
            ]
        }

        for i in range(len(input_strings)):
            self.assertEqual(expected_float_results[i],
                             AttributeParser.parse_attribute(attributes['attribute_rules'][0],
                             input_strings[i]),
                             f"Float was not parsed correctly for input string: {input_strings[i]}")
            self.assertEqual(expected_int_results[i],
                             AttributeParser.parse_attribute(attributes['attribute_rules'][1],
                             input_strings[i]),
                             f"Int was not parsed correctly for input string: {input_strings[i]}")
            self.assertEqual(expected_text_results[i],
                             AttributeParser.parse_attribute(attributes['attribute_rules'][2],
                             input_strings[i]),
                             f"Text was not parsed correctly for input string: {input_strings[i]}")

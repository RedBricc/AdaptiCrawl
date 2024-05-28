import regex
import unittest

from scrapers.ScraperSettings import ScraperSettings
from services import SettingsService
from services import StopwordService
from preprocessing import HtmlCleaner

from bs4 import BeautifulSoup

settings_service = SettingsService.service
StopwordService = StopwordService.service


class HtmlCleanerTest(unittest.TestCase):
    def test_remove_comments(self):
        input_html = ('<html><body><div>'
                      '<a>TEST</a>'
                      '<!-- REMOVE ME -->'
                      '<!-- '
                      '<a>REMOVE ME</a>'
                      ' -->'
                      '<a>I STAY</a>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')

        HtmlCleaner.remove_comments(soup, ScraperSettings())

        self.assertIsNone(soup.find(string=regex.compile('REMOVE ME')), 'comment was not removed')
        self.assertIsNotNone(soup.find(string='TEST'), 'real tag was removed')
        self.assertIsNotNone(soup.find(string='I STAY'), 'real tag was removed')

    def test_inline_css(self):
        input_html = ('<html><head><style>'
                      '.v-card-item-h {color:red}'
                      '.v-card-item-h-spaced {color: green}'
                      'a.v-card-item-sneaky {color: blue}'
                      '* {background-color: purple}'
                      'a > span {color: orange}'
                      '</style></head>'
                      '<body><div>'
                      '<a style="color: white">WHITE</a>'
                      '<a class="v-card-item-h">RED</a>'
                      '<a class="v-card-item-h-spaced">GREEN</a>'
                      '<a class="v-card-item-sneaky">BLUE</a>'
                      '<a class="v-card-item">BACKGROUND</a>'
                      '<a><span>ORANGE</span></a>'
                      '</div></body></html>')
        inlined_css = HtmlCleaner.inline_css(input_html, ScraperSettings())
        soup = BeautifulSoup(inlined_css, 'html.parser')

        self.assertEqual(1, len(soup.findAll(style=regex.compile(r'color:\s*white'))), 'style removed')
        self.assertEqual(1, len(soup.findAll(style=regex.compile(r'color:\s*red'))), 'class not inlined')
        self.assertEqual(1, len(soup.findAll(style=regex.compile(r'color:\s*green'))), 'class with space not inlined')
        self.assertEqual(1, len(soup.findAll(style=regex.compile(r'color:\s*blue'))),
                         'class with specific selector not inlined')
        self.assertEqual(11, len(soup.findAll(style=regex.compile(r'background-color:\s*purple'))),
                         '* selector not inlined')
        self.assertEqual(1, len(soup.findAll(style=regex.compile(r'color:\s*orange'))), 'child selector not inlined')

    def test_remove_excluded_tags(self):
        input_html = ('<html><body><div>'
                      '<script><div>REMOVE ME</div></script>'
                      '<a class="v-card-item"><svg></svg><span>I STAY</span></a>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'excluded_tags': ['script', 'svg']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.remove_excluded_tags(soup, ScraperSettings())

        self.assertIsNone(soup.find('script'), 'script tag not removed')
        self.assertIsNone(soup.find('REMOVE ME'), 'script content not removed')
        self.assertIsNone(soup.find('svg'), 'svg tag not removed')

        self.assertIsNotNone(soup.find(string='I STAY'), 'span tag should not be removed')

    def test_remove_invisible_tags(self):
        input_html = ('<html><body><div>'
                      '<a class="v-card-item" style="display:none"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item" style="color: red;display: none"><span>REMOVE ME</span></a>'
                      '<a hidden><span>AND ME</span></a>'
                      '<a style="visibility: hidden"><span>ME TOO</span></a>'
                      '<a class="v-card-item"><span>I STAY</span></a>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'invisible_tag_regex': ['display:\\s?none', 'visibility:\\s?hidden']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.remove_invisible_tags(soup, ScraperSettings())

        self.assertIsNone(soup.find(string='REMOVE ME'), 'display:none tag not removed')
        self.assertIsNone(soup.find(string='AND ME'), 'hidden tag not removed')
        self.assertIsNone(soup.find(string='ME TOO'), 'visibility:hidden tag not removed')

        self.assertIsNotNone(soup.find(string='I STAY'), 'visible tag was removed')

    def test_remove_non_whitelisted_attributes(self):
        input_html = ('<html><body><div>'
                      '<a class="v-card-item" style="display:none"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item" style="color: red;display: none"><span>REMOVE ME</span></a>'
                      '<a hidden><span>AND ME</span></a>'
                      '<a style="visibility: hidden"><span>ME TOO</span></a>'
                      '<a class="v-card-item"><span>I STAY</span></a>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'whitelisted_attributes': ['class']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.remove_non_whitelisted_attributes(soup, ScraperSettings())

        self.assertEqual([], soup.select('[style]'), 'style attribute not removed')
        self.assertEqual([], soup.select('[hidden]'), 'hidden attribute not removed')

        self.assertNotEqual([], soup.select("[class]"), 'class attribute was removed')

    def test_flatten_text(self):
        input_html = ('<html><body><div>'
                      '<a>FLATTEN'
                      '<b>ME</b>'
                      '</a>'
                      '<a>THIS'
                      '<i>FLATTENS</i>TOO'
                      '</a>'
                      '<p>NOT'
                      '<span>THIS</span>'
                      '</p>'
                      '<a>THIS'
                      '<i>FLATTENS</i>'
                      'EVEN'
                      '<span>NOT THIS</span>'
                      '<b>WHEN</b>'
                      'ITS'
                      '<i>IN</i>'
                      'THE MIDDLE'
                      '</a>'
                      '</div></body></html>')
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'flattened_tags': ['b', 'i']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.flatten_text(soup, ScraperSettings())

        self.assertIsNotNone(soup.find(string='FLATTEN ME'), 'text was not flattened')
        self.assertIsNotNone(soup.find(string='THIS FLATTENS TOO'), 'text in middle was not flattened')

        span_tag = soup.new_tag('span')
        span_tag.string = 'NOT THIS'

        self.assertIsNone(soup.find(tag="p", string='NOT THIS'), 'text was flattened when it should not have been')

        middle_contents = ['THIS FLATTENS EVEN', span_tag, 'WHEN ITS IN THE MIDDLE']
        self.assertIsNotNone(soup.find(lambda tag: tag.contents == middle_contents),
                             'mixed text was not flattened correctly')

    def test_flatten_special_strings(self):
        input_html = ('<html><body>'
                      '<p>'
                      'Special string: <b>EUR</b> is included in this text.'
                      '</p>'
                      '</body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'flattened_special_strings': ['EUR']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.flatten_special_strings(soup, ScraperSettings())

        self.assertIsNotNone(soup.find(string='Special string: EUR is included in this text.'),
                             f'special string was not flattened\n{str(soup.prettify())}')

    def test_remove_empty_tags(self):
        input_html = ('<html><body><div>'
                      '<a id=1></a>'
                      '<a id=2><span></span></a>'
                      '<a id=3><img/></a>'
                      '<a id=4><span>I<b></b>STAY</span></a>'
                      '<a id=5><span>I<b>STAY</b>TOO</span></a>'
                      '</div></body></html>')
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'empty_tags': ['img']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.remove_empty_tags(soup, ScraperSettings())

        self.assertIsNone(soup.find(id='1'), 'empty tag was not removed')
        self.assertIsNone(soup.find(id='2'), 'nested empty tag was not removed')
        self.assertIsNotNone(soup.find(id='3'), 'tag with image was removed')
        self.assertIsNotNone(soup.find(id='4', string='I STAY'), 'tag with text was removed')
        self.assertEqual(3, len(soup.find(id='5').findChild().contents), 'tag with nested text was removed')

    def test_remove_duplicate_whitespace(self):
        input_html = ('<html><body><div>'
                      '<a id=1>SPACE   HERE</a>'
                      '</div></body></html>')
        soup = BeautifulSoup(input_html, 'html.parser')

        HtmlCleaner.remove_duplicate_whitespace(soup, ScraperSettings())

        self.assertIsNotNone(soup.find(id='1', string='SPACE HERE'), 'duplicate whitespace was not removed')

    def test_remove_punctuation_whitespace(self):
        input_html = ('<html><body><div>'
                      '<a id=1>SPACE HERE .</a>'
                      '<a id=2>SPACE HERE !</a>'
                      '<a id=3>SPACE HERE ? !</a>'
                      '</div></body></html>')
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'punctuation_marks': ['!', '?']}
        settings_service.mock_catalog_settings(settings)

        HtmlCleaner.remove_punctuation_whitespace(soup, ScraperSettings())

        self.assertIsNotNone(soup.find(id='1', string='SPACE HERE .'), 'whitespace before "." was removed')
        self.assertIsNotNone(soup.find(id='2', string='SPACE HERE!'), 'whitespace before "!" was not removed')
        self.assertIsNotNone(soup.find(id='3', string='SPACE HERE?!'), 'whitespace before "?!" was not removed')

    def test_inline_images(self):
        input_html = ('<html><body><div>'
                      '<a style="background-image: url(\'example.com/image1.jpg\')">IMAGE 1</a>'
                      '<a style="background-image: url(\'image2.jpg\')">IMAGE 2</a>'
                      '<img src="example.com/image3.jpg"/>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')

        HtmlCleaner.inline_images(soup, ScraperSettings())

        self.assertIsNotNone(soup.find(name='img', src='example.com/image1.jpg'), 'Static image was not inlined')
        self.assertIsNotNone(soup.find(name='img', src='image2.jpg'), 'Relative image was not inlined')
        self.assertIsNotNone(soup.find(name='img', src='example.com/image3.jpg'), 'Image tag was removed')


if __name__ == '__main__':
    unittest.main()

import regex
import unittest

from services import SettingsService
from services import StopwordService
from preprocessing import HtmlCleaner

from bs4 import BeautifulSoup

SettingsService = SettingsService.service
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

        HtmlCleaner.remove_comments(soup)

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
        inlined_css = HtmlCleaner.inline_css(input_html, None)
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
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.remove_excluded_tags(soup)

        self.assertIsNone(soup.find('script'), 'script tag not removed')
        self.assertIsNone(soup.find('REMOVE ME'), 'script content not removed')
        self.assertIsNone(soup.find('svg'), 'svg tag not removed')

        self.assertIsNotNone(soup.find(string='I STAY'), 'span tag should not be removed')

    def test_remove_stopwords(self):
        input_html = ('<html><body><div>'
                      '<a class="v-card-item up"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item"><span>I STAY</span></a>'
                      '</div></body></html>')

        soup = BeautifulSoup(input_html, 'html.parser')
        stopwords = ['i', 'me', 'up']
        StopwordService.mock_stopwords(stopwords)

        HtmlCleaner.remove_stopwords(soup)

        self.assertIsNone(soup.find(string='REMOVE ME'), 'stopword "me" not removed')
        self.assertIsNone(soup.find(string='I STAY'), 'stopword "i" not removed')

        self.assertIsNotNone(soup.find('a', class_='v-card-item up'), 'stopwords should not be removed outside of text')
        self.assertIsNotNone(soup.find(string='STAY'), 'non-stopword text was removed')
        self.assertIsNotNone(soup.find(string='REMOVE'), 'non-stopword text was removed')

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
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.remove_invisible_tags(soup)

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
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.remove_non_whitelisted_attributes(soup)

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
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.flatten_text(soup)

        self.assertIsNotNone(soup.find(string='FLATTEN ME'), 'text was not flattened')
        self.assertIsNotNone(soup.find(string='THIS FLATTENS TOO'), 'text in middle was not flattened')

        span_tag = soup.new_tag('span')
        span_tag.string = 'NOT THIS'

        self.assertIsNone(soup.find(tag="p", string='NOT THIS'), 'text was flattened when it should not have been')

        middle_contents = ['THIS FLATTENS EVEN', span_tag, 'WHEN ITS IN THE MIDDLE']
        self.assertIsNotNone(soup.find(lambda tag: tag.contents == middle_contents),
                             'mixed text was not flattened correctly')

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
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.remove_empty_tags(soup)

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

        HtmlCleaner.remove_duplicate_whitespace(soup)

        self.assertIsNotNone(soup.find(id='1', string='SPACE HERE'), 'duplicate whitespace was not removed')

    def test_remove_punctuation_whitespace(self):
        input_html = ('<html><body><div>'
                      '<a id=1>SPACE HERE .</a>'
                      '<a id=2>SPACE HERE !</a>'
                      '<a id=3>SPACE HERE ? !</a>'
                      '</div></body></html>')
        soup = BeautifulSoup(input_html, 'html.parser')
        settings = {'punctuation_marks': ['!', '?']}
        SettingsService.mock_catalog_settings(settings)

        HtmlCleaner.remove_punctuation_whitespace(soup)

        self.assertIsNotNone(soup.find(id='1', string='SPACE HERE .'), 'whitespace before "." was removed')
        self.assertIsNotNone(soup.find(id='2', string='SPACE HERE!'), 'whitespace before "!" was not removed')
        self.assertIsNotNone(soup.find(id='3', string='SPACE HERE?!'), 'whitespace before "?!" was not removed')

    def test_clean_data(self):
        input_html = ('<html>'
                      '<head><style>'
                      '.v-card-item-h {display:none}'
                      '.v-card-item-h-spaced {display: none}'
                      '.v-card-item-sneaky {visibility: hidden}'
                      '</style></head>'
                      '<body><div>'
                      '<script><div>EXCLUDE ME</div></script>'
                      '<a class="v-card-item" style="display:none"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item" style="color: red;display: none"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item-h"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item-h-spaced"><span>REMOVE ME</span></a>'
                      '<a hidden><span>REMOVE ME</span></a>'
                      '<!-- '
                      '<a>COMMENT</a>'
                      ' -->'
                      '<a style="visibility: hidden"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item-sneaky"><span>REMOVE ME</span></a>'
                      '<a class="v-card-item up"><span>I <s id="empty"></s><b>STAY</b> HERE    !</span></a>'
                      '<a id="space">SPACE   HERE</a>'
                      '<a id="nonEmpty"><img/></a>'
                      '</div></body></html>')
        stopwords = ['i', 'me', 'up']
        settings = {
            'excluded_tags': ['script', 'svg'],
            'whitelisted_attributes': ['class', 'id'],
            'flattened_tags': ['b'],
            'punctuation_marks': ['!'],
            'empty_tags': ['img'],
            'invisible_tag_regex': ['display:\\s?none', 'visibility:\\s?hidden']
        }
        SettingsService.mock_catalog_settings(settings)
        StopwordService.mock_stopwords(stopwords)

        soup = HtmlCleaner.clean_data(input_html, None)

        self.assertIsNone(soup.find('style'), 'css was not fully inlined')
        self.assertIsNone(soup.find(string='REMOVE ME'), 'invisible tag was not removed')
        self.assertIsNone(soup.find(string='EXCLUDE ME'), 'excluded tag was not removed')
        self.assertIsNone(soup.find(string='I STAY'), 'stopword was not removed')
        self.assertIsNone(soup.find(string='REMOVE'), 'invisible or excluded tag was not removed')
        self.assertIsNone(soup.find(string='STAY  HERE'), 'duplicate whitespace was not removed')
        self.assertIsNone(soup.find(string=regex.compile('HERE !')), 'whitespace before punctuation was not removed')
        self.assertIsNone(soup.find(id='empty'), 'empty tag was not removed')
        self.assertEqual([], soup.select('[style]'), 'style attribute was not removed')
        self.assertEqual([], soup.select('[hidden]'), 'hidden attribute was not removed')

        self.assertIsNotNone(soup.find(string=regex.compile('STAY.+')), 'non-stopword text was removed')
        self.assertIsNotNone(soup.find(string='STAY HERE!'), 'text was not flattened')
        self.assertIsNotNone(soup.find('a', class_='up'), 'stopwords should not be removed outside of text')
        self.assertIsNotNone(soup.find(id='nonEmpty'), 'tag with image was removed')
        self.assertIsNotNone(soup.find(id='space', string='SPACE HERE'), 'duplicate whitespace was not removed')
        self.assertNotEqual([], soup.select("[class]"), 'class attribute was removed')
        self.assertIsNone(soup.find(string=regex.compile('COMMENT')), 'comment was not removed')


if __name__ == '__main__':
    unittest.main()

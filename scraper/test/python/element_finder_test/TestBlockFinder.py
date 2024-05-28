import unittest

from bs4 import BeautifulSoup

from element_finder import BlockFinder


input_html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Test</title>
    </head>
    <body>
        <div class="block" id="block1">
            <h1>Block 1</h1>
            <p>Block 1 content</p>
        </div>
        <div class="block" id="block2">
            <h1>Block 2</h1>
            <p>Block 2 content</p>
        </div>
        <div class="container">
            <div class="wrapper">
                <div class="block" id="block3">
                    <h1>Block 3</h1>
                    <p>Block 3 content</p>
                </div>
            </div>
            <div class="block" id="block4">
                <h1>Block 4</h1>
                <p>Block 4 content</p>
            </div>
            <div class="block" id="block5">
                <h1>Block 5</h1>
                <p>Block 5 content</p>
            </div>
        </div>
    </body>
"""


class BlockFinderTest(unittest.TestCase):
    def test_get_distance(self):
        soup = BeautifulSoup(input_html, 'html.parser')
        blocks = soup.find_all('div', class_='block')

        distance = BlockFinder.get_distance(blocks[0], blocks[0])
        self.assertEqual(0, distance, "Distance between the tag and itself should be 0")

        distance = BlockFinder.get_distance(blocks[0], blocks[1])
        self.assertEqual(1, distance, "Distance between sibling blocks should be 1")

        distance = BlockFinder.get_distance(blocks[0], blocks[2])
        self.assertEqual(3, distance, "Wrong distance between three far apart blocks")

        distance = BlockFinder.get_distance(blocks[2], blocks[0])
        self.assertEqual(3, distance, "Block order should not matter")

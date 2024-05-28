import unittest
from pathlib import Path

from services.ImageService import RecordImage


def load_image(test_image: str):
    image_path = Path(__file__).parent.joinpath(f"../../resources/images/{test_image}").resolve()
    with open(image_path, 'rb') as file:
        return RecordImage(None, test_image.split('.')[-1], file.read())


class ImageServiceTest(unittest.TestCase):
    def test_get_hash(self):
        image = RecordImage(None, None, None)
        self.assertIsNone(image.hash, "Hash was not None when image was None")

        image = RecordImage(None, None, b'')
        self.assertIsNone(image.hash, "Hash was not None when image was empty")

        image = RecordImage(None, None, b'123')
        self.assertEqual('a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3', image.hash,
                         "Hash was not correct")

        image1 = load_image('test_img_1.jpeg')
        image2 = load_image('test_img_2.jpeg')

        self.assertEqual(image1.image, image2.image, "Images were not equal")
        self.assertEqual(image1.hash, image2.hash, "Hashes were not equal")

        self.assertNotEqual(image.hash, image1.hash,
                            "Hashes were equal for images with different content")

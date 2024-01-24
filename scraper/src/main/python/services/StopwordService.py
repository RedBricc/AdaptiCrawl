import logging
from pathlib import Path


class StopwordService:
    def __init__(self):
        imported_stopwords = []

        # based on nltk.corpus.stopwords.words('english')
        stopwords_path = Path(__file__).parent.joinpath('../../resources/stopwords.txt').resolve()
        with open(stopwords_path, 'r') as f:
            for line in f:
                imported_stopwords.append(line)

        if len(imported_stopwords) == 0:
            logging.warning("No stopwords found")

        self.stopwords = imported_stopwords

    def get_stopwords(self):
        return self.stopwords

    def mock_stopwords(self, mock_stopwords):
        self.stopwords = mock_stopwords


service = StopwordService()

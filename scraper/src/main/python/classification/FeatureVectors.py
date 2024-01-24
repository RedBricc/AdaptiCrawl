from sklearn.feature_extraction.text import CountVectorizer

from services import SettingsService

SettingsService = SettingsService.service


def generate_vectors(corpus):
    max_features = SettingsService.get_catalog_setting('max_features')

    vectorizer = CountVectorizer(max_features=max_features, strip_accents='unicode')
    vectorizer.fit_transform(corpus)

    return vectorizer.get_feature_names_out()

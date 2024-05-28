from sklearn.feature_extraction.text import CountVectorizer

from services import SettingsService

settings_service = SettingsService.service


# Unused, intended for use with classifiers. May be used in the future.
def generate_vectors(corpus):
    max_features = settings_service.get_catalog_setting('max_features')

    vectorizer = CountVectorizer(max_features=max_features, strip_accents='unicode')
    vectorizer.fit_transform(corpus)

    return vectorizer.get_feature_names_out()

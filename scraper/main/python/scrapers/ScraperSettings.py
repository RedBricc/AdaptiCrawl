from enum import Enum


class ScraperType(Enum):
    TEST = 'test'
    CATALOG = 'catalog'
    VDP = 'vdp'
    CATALOG_STATIC = 'catalog_static'


class LocaleConfiguration:
    def __init__(self, configuration: dict = None, scraper_type=ScraperType.TEST):
        if not isinstance(configuration, dict):
            configuration = {}
        self.interaction_buttons = configuration.get('interaction_buttons') \
            if 'interaction_buttons' in configuration else []
        self.ignored_cleaning_steps = configuration.get('ignored_cleaning_steps') \
            if 'ignored_cleaning_steps' in configuration else []
        self.preferred_pagination_handler = configuration.get('preferred_pagination_handler')
        self.ignore_min_record_count = configuration.get('ignore_min_record_count') \
            if 'ignore_min_record_count' in configuration else False
        self.translate_page = configuration.get('translate_page') \
            if 'translate_page' in configuration else True if scraper_type == ScraperType.VDP else False
        self.use_proxy = configuration.get('use_proxy') \
            if 'use_proxy' in configuration else False
        self.record_id = configuration.get('record_id')
        self.record_alias = configuration.get('record_alias')


class ScraperSettings:
    def __init__(self, scraper_type: ScraperType = ScraperType.TEST, domain='', locale='', url=None,
                 configuration: LocaleConfiguration | dict = None,
                 run_id=0, save_trees=False, driver=None, proxy=None):
        self.scraper_type = scraper_type
        self.domain = domain
        self.locale = locale
        self.url = url
        self.run_id = run_id
        self.driver = driver
        self.proxy = proxy
        self.save_trees = save_trees

        if isinstance(configuration, LocaleConfiguration):
            self.configuration = configuration
        else:
            self.configuration = LocaleConfiguration(configuration, scraper_type)


class BatchSettings:
    def __init__(self, proxy=None, settings: list[ScraperSettings] = None):
        self.proxy = proxy
        self.settings = settings or []


class StopException(Exception):
    pass


import logging
import sys
import traceback

import schedule

from db import Credentials
from db import DatabaseConnector
from scrapers.ScraperSettings import ScraperType

required_scraper_settings = [
    'catalog_scraper_settings',
    'vdp_scraper_settings',
    'catalog_attribute_rules',
    'vdp_attribute_rules',
    'target_domains',
    'static_scraper_settings',
    'webscraper_settings',
    'scheduler_settings'
]


def load_settings(scheduler_id):
    if scheduler_id is None:
        logging.warning("Missing scheduler_id!")
        return {}

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute("SELECT name, value FROM settings WHERE scheduler_id = %s", (scheduler_id,))
        settings = cursor.fetchall()

        settings_dict = {}
        for setting in settings:
            settings_dict[setting[0]] = setting[1]

        return settings_dict


class SettingsException(Exception):
    pass


class SettingsService:
    def __init__(self, scheduler_id, setting_type):
        self.scheduler_id = scheduler_id.upper()
        self.setting_type = setting_type
        self.settings = None
        self.update_settings()
        schedule.every(10).minutes.do(self.update_settings)

    def update_settings(self):
        if self.scheduler_id == 'TEST':
            logging.info("Running in test mode, settings can be set using mock methods")
            return

        logging.info("Updating settings...")
        try:
            imported_settings = load_settings(self.scheduler_id)
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except:
            logging.error(f"Failed to update settings: {traceback.format_exc()}")
            return

        if len(imported_settings) == 0:
            raise SettingsException(f"No settings found for scheduler_id {self.scheduler_id}")

        if self.setting_type == 'SCRAPER':
            for setting in required_scraper_settings:
                if setting not in imported_settings:
                    raise SettingsException(f"Settings missing required field: {setting}")

        self.settings = imported_settings
        logging.info("Settings updated!")

    def get_catalog_setting(self, name, default=None):
        return self.get_setting(name, 'catalog_scraper_settings', default=default)

    def get_vdp_setting(self, name, default=None):
        return self.get_setting(name, 'vdp_scraper_settings', default=default)

    def get_scraper_setting(self, name, scraper_type: ScraperType, default=None):
        return self.get_setting(name, f'{scraper_type.value}_scraper_settings', default=default)

    def get_static_setting(self, setting_group, name, default=None):
        return self.get_setting(name, setting_group, default=default)

    def get_webscraper_setting(self, name, default=None):
        return self.get_setting(name, 'webscraper_settings', default=default)

    def get_scheduler_setting(self, name, default=None):
        return self.get_setting(name, 'scheduler_settings', default=default)

    def get_attribute_rules(self, scraper_type: ScraperType, default=None):
        if default is None:
            default = []
        return self.get_setting(f'{scraper_type.value}_attribute_rules', default=default)

    def get_target_domains(self, default=None):
        if default is None:
            default = {}
        return self.get_setting('target_domains', default=default)

    def get_static_settings(self, default=None):
        return self.get_setting('static_scraper_settings', default=default)

    def get_api_setting(self, name, default=None):
        return self.get_setting(name, 'api_settings', default=default)

    def mock_catalog_settings(self, mock_settings):
        self.create_mock_settings('test_scraper_settings', mock_settings)

    def mock_attribute_settings(self, mock_settings):
        self.create_mock_settings('test_attribute_rules', mock_settings)

    def create_mock_settings(self, setting_type, mock_settings):
        self.set_settings({setting_type: mock_settings})

    def get_setting(self, name, setting_group_name=None, default=None):
        setting_group = self.settings
        if setting_group_name is not None:
            setting_group = self.get_setting(setting_group_name, default={})

        setting = setting_group.get(name)

        if setting is not None:
            return setting
        else:
            logging.error(f"\n{(str(setting_group_name) + ' ') or ''}"
                          f"Missing requested field: {name}\nReturning {default}")
        return default

    def set_settings(self, new_settings):
        self.settings = new_settings

    @staticmethod
    def is_prod():
        if Credentials.ENVIRONMENT == 'PROD':
            return True
        return False

    @staticmethod
    def is_stage():
        if Credentials.ENVIRONMENT == 'STAGE':
            return True
        return False

    @staticmethod
    def is_dev():
        if Credentials.ENVIRONMENT == 'DEV':
            return True
        return False

    @staticmethod
    def get_env():
        return Credentials.ENVIRONMENT


arg_setting_type = 'SCRAPER'
try:
    arg_scheduler_id = sys.argv[1]

    if arg_scheduler_id.lower().find('test') != -1:
        logging.warning("Test mode detected!")
        arg_scheduler_id = 'TEST'
    elif arg_scheduler_id.lower().find('api') != -1:
        arg_scheduler_id = 'API'
        arg_setting_type = 'API'
except SystemExit or KeyboardInterrupt:
    exit(-1)
except:
    logging.warning(f"Missing scheduler_id argument. Running in TEST mode!")
    arg_scheduler_id = 'TEST'

service = SettingsService(arg_scheduler_id, arg_setting_type)

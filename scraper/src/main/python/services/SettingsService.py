import json
import logging
import schedule
from pathlib import Path

from db import Credentials


class SettingsService:
    def __init__(self):
        self.settings = None
        self.update_settings()

    def update_settings(self):
        logging.info("Updating settings...")
        settings_path = Path(__file__).parent.joinpath('../../resources/settings.json').resolve()
        with open(settings_path, 'r', encoding='utf-8') as f:
            imported_settings = json.load(f)

        if len(imported_settings) == 0:
            raise Exception("No settings found")

        if imported_settings.get('catalog_scraper_settings') is None:
            raise Exception("Settings file is missing required field: catalog_scraper_settings")

        if imported_settings.get('static_scraper_settings') is None:
            raise Exception("Settings file is missing required field: static_scraper_settings")

        if imported_settings.get('webscraper_settings') is None:
            raise Exception("Settings file is missing required field: webscraper_settings")

        if imported_settings.get('scheduler_settings') is None:
            raise Exception("Settings file is missing required field: scheduler_settings")

        self.settings = imported_settings
        logging.info("Settings updated!")

    def get_catalog_setting(self, name):
        catalog_settings = self.get_group_setting(self.settings, 'catalog_scraper_settings')
        return self.get_group_setting(catalog_settings, name)

    def get_static_setting(self, setting_group, name):
        static_settings = self.get_static_settings()
        group_settings = self.get_group_setting(static_settings, setting_group)
        return self.get_group_setting(group_settings, name)

    def get_webscraper_setting(self, name):
        webscraper_settings = self.get_group_setting(self.settings, 'webscraper_settings')
        return self.get_group_setting(webscraper_settings, name)

    def get_scheduler_setting(self, name):
        scheduler_settings = self.get_group_setting(self.settings, 'scheduler_settings')
        return self.get_group_setting(scheduler_settings, name)

    def get_static_settings(self):
        return self.get_group_setting(self.settings, 'static_scraper_settings')

    def mock_catalog_settings(self, mock_settings):
        self.create_mock_settings('catalog_scraper_settings', mock_settings)

    def create_mock_settings(self, setting_type, mock_settings):
        self.set_settings({setting_type: mock_settings})

    def set_settings(self, new_settings):
        self.settings = new_settings

    def get_settings(self):
        return self.settings

    def get_setting(self, name):
        setting = self.settings.get(name)
        return self.verify_setting(setting, name)

    def get_group_setting(self, setting_group, name):
        setting = setting_group.get(name)
        return self.verify_setting(setting, name)

    def verify_setting(self, setting, name):
        if setting is not None:
            return setting
        else:
            logging.error(f"\nSettings file is missing requested field: {name} "
                            f"\nSettings: {self.settings}"
                            f"\nReturning empty settings!")
            return {}

    def is_prod(self):
        if Credentials.ENVIRONMENT == 'prod':
            return True
        return False

    def is_stage(self):
        if Credentials.ENVIRONMENT == 'stage':
            return True
        return False

    def is_dev(self):
        if Credentials.ENVIRONMENT == 'dev':
            return True
        return False

    def get_env(self):
        return Credentials.ENVIRONMENT


service = SettingsService()
schedule.every(10).minutes.do(service.update_settings)

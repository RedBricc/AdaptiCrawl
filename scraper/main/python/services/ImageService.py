import hashlib
import logging
import timeit
import traceback
from datetime import datetime
from pathlib import Path

from office365.runtime.auth.client_credential import ClientCredential
from office365.runtime.client_request_exception import ClientRequestException
from office365.sharepoint.client_context import ClientContext

from db import Credentials, DatabaseConnector
from scrapers import ScraperSettings
from services import SettingsService

settings_service = SettingsService.service
relative_urls = {}

SCRAPER_SCREENSHOT_FOLDER = 'scraper_screenshots'
RECORD_IMAGE_FOLDER = 'record_images'


def initialize_sharepoint():
    """
    Initializes the sharepoint directory.
    """
    create_sharepoint_directory(RECORD_IMAGE_FOLDER)
    create_sharepoint_directory(SCRAPER_SCREENSHOT_FOLDER)


def authenticate():
    client_credentials = ClientCredential(Credentials.SHAREPOINT_ID, Credentials.SHAREPOINT_SECRET)
    client_context = ClientContext(Credentials.SHAREPOINT_URL).with_credentials(client_credentials)

    return client_context.web


def create_sharepoint_directory(dir_name: str):
    """
    Creates a folder in the sharepoint directory.
    :param dir_name: The name of the directory to create.
    :return: The relative url of the directory.
    """
    if not (settings_service.is_stage() or settings_service.is_prod()):
        logging.info(f"Screenshot saving not enabled for {settings_service.get_env()} mode")
        return

    if dir_name is None or dir_name == '':
        logging.error(f"Invalid directory name: {dir_name}")
        return

    result = authenticate().folders.add(f'Shared Documents/BI/{dir_name}').execute_query()

    if result:
        relative_url = f'Shared Documents/BI/{dir_name}'
        relative_urls[dir_name] = relative_url
        return relative_url


def save_file(file, file_name, dest_folder):
    """
    Saves a file to the sharepoint directory.
    :param file: The file to save.
    :param file_name: The name of the file.
    :param dest_folder: The relative url of the directory to save the file to.
    :return: The sharepoint url of the file.
    """
    if not (settings_service.is_stage() or settings_service.is_prod()):
        logging.info(f"Screenshot saving not enabled for {settings_service.get_env()} mode")
        return None

    if file is None or file_name is None or dest_folder is None or file_name == '' or dest_folder == '':
        logging.error(f"Invalid file: {file_name} or destination folder: {dest_folder} or file name: {file_name}")
        return None

    try:
        folder_path = relative_urls.get(dest_folder)
        if folder_path is None:
            folder_path = create_sharepoint_directory(dest_folder)
        target_folder = authenticate().get_folder_by_server_relative_url(folder_path)

        try:
            target_folder.upload_file(file_name, file).execute_query()
        except ClientRequestException:
            if not check_if_exists(file_name, dest_folder):
                raise Exception(f"Failed to upload file: {file_name} to folder: {dest_folder}!")

        return f"{Credentials.SHAREPOINT_URL}/{folder_path}/{file_name}"
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Failed to save file: {file_name} to folder: {dest_folder}!\n{traceback.format_exc()}")
        return None


def check_if_exists(file_name, dest_folder):
    """
    Checks if a file exists in the sharepoint directory.
    :param file_name: The name of the file.
    :param dest_folder: The relative url of the directory to check for the file.
    :return: True if the file exists, False if it does not.
    """
    if not (settings_service.is_stage() or settings_service.is_prod()):
        logging.info(f"Sharepoint file check not enabled for {settings_service.get_env()} mode")

    if file_name is None or dest_folder is None or file_name == '' or dest_folder == '':
        logging.error(f"Invalid file: {file_name} or destination folder: {dest_folder}")
        return False

    try:
        file_url = f"{relative_urls.get(dest_folder)}/{file_name}"
        file = authenticate().get_file_by_server_relative_url(file_url).get().execute_query()
        return file.exists
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        return False


def save_screenshot(driver, scraper_settings):
    """
    Saves a screenshot and attempts to upload it to the Sharepoint directory.
    """
    file_name = (f"{scraper_settings.domain}_{scraper_settings.locale.replace(':', '_')}"
                 f"_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png")
    folder_path = Path(__file__).parent.joinpath('../../../../screenshots').resolve()
    path_string = str(folder_path).replace('\\', '/')

    file_path = f"{path_string}/{file_name}"

    try:
        result = driver.save_screenshot(file_path)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        result = False

    if result is False:
        logging.error("Error while trying to save screenshot!")
        return

    if not (settings_service.is_stage() or settings_service.is_prod()):
        logging.info(f"Screenshot uploading not enabled for {settings_service.get_env()} mode")
        return

    if scraper_settings.run_id is None or file_path is None or file_path == '':
        logging.error(f"Invalid run id: {scraper_settings.run_id} or screenshot path: {file_path}")
        return

    dest_folder = f'{SCRAPER_SCREENSHOT_FOLDER}/run_{scraper_settings.run_id}'

    with open(file_path, 'rb') as file:
        save_file(file, file_name, dest_folder)

    # delete local file
    Path(file_path).unlink()


def get_records_with_images(scraper_settings: ScraperSettings):
    start = timeit.default_timer()

    upload_record_images = settings_service.get_catalog_setting('upload_record_images')
    hash_record_images = settings_service.get_catalog_setting('hash_record_images')

    image_sql = ("SELECT alias FROM records "
                 "JOIN scraping_sessions ON scraping_sessions.id = records.scraping_session_id "
                 "WHERE scraping_sessions.domain = %s AND scraping_sessions.locale = %s")

    if upload_record_images is True:
        image_sql += " AND records.image_link IS NOT NULL"

    if hash_record_images is True:
        image_sql += " AND records.image_hash IS NOT NULL"

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute(image_sql,
                       (scraper_settings.domain, scraper_settings.locale,))
        records_with_images = cursor.fetchall()

        logging.log(19, f"DB > Get records with images: {timeit.default_timer() - start:.3f}s")
        return [record[0] for record in records_with_images]


def get_default_images():
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        default_image_sql = "SELECT hash FROM default_images"

        start = timeit.default_timer()
        cursor.execute(default_image_sql)
        default_images = cursor.fetchall()
        logging.log(19, f"DB > Get default images: {timeit.default_timer() - start:.3f}s")

    return [image[0] for image in default_images]


initialize_sharepoint()


class RecordImage:
    def __init__(self, link, extension, image):
        self.link = link
        self.extension = extension
        self.image = image
        self.hash = self.get_hash()

    def save(self, image_name):
        """
        Saves an image to the configured sharepoint directory.
        """
        if not (settings_service.is_stage() or settings_service.is_prod()):
            logging.info(f"Image saving not enabled for {Credentials.ENVIRONMENT} mode")
            return settings_service.get_env()

        upload_record_images = settings_service.get_catalog_setting('upload_record_images')
        if upload_record_images is False:
            logging.info("Image saving disabled in settings")
            return None

        if (self.image is None or image_name is None or image_name == ''
                or self.extension is None or self.extension == ''):
            logging.error(f"Invalid image: {self.image} or image name: {image_name} or extension: {self.extension}")
            return None

        return save_file(self.image, f"{image_name}.{self.extension}", RECORD_IMAGE_FOLDER)

    def get_hash(self):
        if self.image is None or self.image == b'':
            return None

        return hashlib.sha256(self.image).hexdigest()

import logging
import timeit
import traceback
from multiprocessing import Event

from element_finder import BlockFinder
from preprocessing import HtmlCleaner, ValueTagger
from scrapers import WebScraper
from scrapers.ScraperSettings import ScraperSettings, ScraperType, StopException
from scrapers.WebScraper import save_tree
from services import LoggingService, ImageService, SettingsService, VdpService

settings_service = SettingsService.service


class LowFieldCountException(Exception):
    pass


def scrape(scraper_settings: ScraperSettings, run_timeout_event, process_timeout):
    start = timeit.default_timer()

    logging.info(f"Scraping VDP of {scraper_settings.domain}({scraper_settings.locale}) record: "
                 f"{scraper_settings.url} with proxy: {scraper_settings.proxy}")

    driver = WebScraper.open_page(scraper_settings)
    try:
        indexed_soup = WebScraper.get_indexed_soup(driver, scraper_settings)
        WebScraper.close_page(driver)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        raise StopException(f"Failed to get indexed soup: {scraper_settings.url}\n{traceback.format_exc()}")

    cleaned_soup = HtmlCleaner.clean_data(indexed_soup, scraper_settings)
    tagged_soup = ValueTagger.tag_values(cleaned_soup, scraper_settings)

    if scraper_settings.save_trees is True:
        save_tree('cleaned.html', cleaned_soup)
        save_tree('tagged.html', tagged_soup)

    default_images = ImageService.get_default_images()

    # The page may contain multiple record blocks, but we only need the one that this VDP is about
    record_blocks = BlockFinder.find_blocks(tagged_soup, None, scraper_settings,
                                             default_images=default_images,
                                             record_alias=scraper_settings.configuration.record_alias,
                                             prioritize_first=True)

    if len(record_blocks) == 0:
        raise RuntimeError('No record blocks found')

    record_block = record_blocks[0]
    record_block['id'] = scraper_settings.configuration.record_id

    empty_field_threshold = settings_service.get_vdp_setting('empty_field_threshold')
    empty_field_count = VdpService.count_empty_fields(record_block)

    fuzzy_record_block = None
    if empty_field_count >= empty_field_threshold:
        check_timeout(run_timeout_event, start, process_timeout)

        logging.warning(f"Record block has too few filled fields, reading information from the body instead.")
        fuzzy_record_block = BlockFinder.parse_blocks([tagged_soup], None, scraper_settings,
                                                       records_with_images=[],
                                                       default_images=default_images,
                                                       record_alias=scraper_settings.configuration.record_alias)[0]

    if fuzzy_record_block is not None:
        for key, value in fuzzy_record_block.items():
            if record_block[key] is None or record_block[key] == '':
                record_block[key] = value

    empty_field_count = VdpService.count_empty_fields(record_block)
    if empty_field_count >= empty_field_threshold:
        high_priority_fields = settings_service.get_vdp_setting('high_priority_fields')

        if high_priority_fields is not None:
            for key in high_priority_fields:
                if record_block[key] is not None and record_block[key] != '':
                    return record_block

        raise LowFieldCountException(
            f"Record block has too few filled fields: {len(record_block) - empty_field_count}")

    return record_block


def check_timeout(run_timeout_event, start, process_timeout):
    if run_timeout_event.is_set():
        raise StopException("Run timeout event set, stopping scraping")
    elif timeit.default_timer() - start > process_timeout:
        raise StopException("Process timeout reached, stopping scraping")


if __name__ == "__main__":
    LoggingService.setup_logger(dev_log_level=18)
    configuration = {
        'record_id': '10482920',
        'record_alias': '10482920.html'
    }

    target = ScraperSettings(
        scraper_type=ScraperType.VDP,
        domain='bravoauto',
        locale='ee',
        url='https://bravoauto.lt/automobiliai/bmw/bmw-330-20-automatin-benzinas-elektra-17007',
        driver=WebScraper.get_driver(),
        configuration=configuration,
        save_trees=True
    )

    logging.info(scrape(target, Event(), process_timeout=300))

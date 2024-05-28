import json
import logging
import sys
from itertools import chain

import Scheduler
from scrapers import CatalogScraper, VdpScraper, WebScraper
from scrapers.ScraperSettings import ScraperSettings, ScraperType
from services import LoggingService, ProxyService


def debug_run(scraper_type, domain, locale, url, configuration, run_id):
    LoggingService.setup_logger()
    proxy = ProxyService.find_first_proxy()
    driver = WebScraper.get_driver(proxy)
    scraper_settings = ScraperSettings(
        scraper_type=scraper_type,
        domain=domain,
        locale=locale,
        url=url,
        configuration=configuration,
        run_id=run_id,
        driver=driver,
        save_trees=True
    )

    print(f"Domain: {domain}, Locale: {locale}, URL: {url}, "
          f"Configuration: {configuration}, Run ID: {run_id}, Proxy: {proxy}")

    if scraper_type == ScraperType.VDP:
        scraper = VdpScraper
    elif scraper_type == ScraperType.CATALOG:
        scraper = CatalogScraper
    else:
        raise ValueError(f"Unknown scraper type: {scraper_type}")

    Scheduler.try_scrape_page(scraper, scraper_settings, Scheduler.save_catalog_scrape, 'debugging')


if __name__ == '__main__':
    logging.getLogger().handlers = []
    logging.basicConfig(level=18)
    script, arg_scheduler_id, arg_scraper_type, arg_domain, arg_locale, arg_url, arg_config, arg_run_id, *_ = chain(sys.argv, [None] * 7)

    if (arg_scraper_type is None or arg_scheduler_id is None
            or arg_domain is None or arg_locale is None or arg_url is None):
        logging.error("Usage: DebugRun.py <scheduler_id> <scraper_type> <domain> <locale> <url> <config> <run_id>")
        sys.exit(1)

    arg_config = json.loads(arg_config)
    arg_scraper_type = arg_scraper_type.lower()

    try:
        arg_scraper_type = ScraperType(arg_scraper_type)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Unknown scraper type: {arg_scraper_type}")
        sys.exit(1)

    debug_run(ScraperType(arg_scraper_type), arg_domain, arg_locale, arg_url, arg_config, arg_run_id)

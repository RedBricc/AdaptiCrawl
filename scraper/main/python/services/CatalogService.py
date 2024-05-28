import logging
import timeit
import traceback
from datetime import datetime, timedelta

from db import DatabaseConnector
from scrapers.ScraperSettings import ScraperSettings
from services import SettingsService, ImageService

settings_service = SettingsService.service


def save_run(scraper_type):
    run_sql = ("INSERT INTO runs (start_time, end_time, scheduler_id, scraper_type)"
               " VALUES (DEFAULT, NULL, %s, %s) RETURNING id;")

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute(run_sql, (settings_service.scheduler_id, scraper_type.value.upper(),))
        connection.commit()
        run_id = cursor.fetchone()[0]

        logging.info(f"Run id: {run_id}")

        return run_id


def end_run(run_id):
    start_sql = "SELECT start_time FROM runs WHERE id = %s;"
    run_sql = "UPDATE runs SET end_time = %s, duration = %s WHERE id = %s;"

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute(start_sql, (run_id,))
        start_time = cursor.fetchone()[0]

        tz_info = start_time.tzinfo
        end_time = datetime.now(tz_info)

        cursor.execute(run_sql, (end_time, end_time - start_time, run_id,))

        logging.info(f"End time: {datetime.now()} Duration: {end_time - start_time}")

        connection.commit()


def save_scrape(scraper_settings: ScraperSettings, records, message, scraping_time):
    scrape_sql = ("INSERT INTO scraping_sessions (domain, locale, url, found_count, result, scraping_time, run_id) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;")

    domain = scraper_settings.domain
    locale = scraper_settings.locale
    url = scraper_settings.url
    run_id = scraper_settings.run_id

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        if records is None:
            cursor.execute(scrape_sql, (domain, locale, url, '0', message, scraping_time, run_id))
        else:
            if scraper_settings.scraper_type == 'VDP':
                record_count = 1
            else:
                record_count = len(records)

            cursor.execute(scrape_sql, (domain, locale, url, record_count, message, scraping_time, run_id))

        connection.commit()
        scrape_id = cursor.fetchone()[0]

        return scrape_id


def update_scrape(scrape_id, records, message, scraping_time):
    scrape_sql = ("UPDATE scraping_sessions SET found_count = %s, result = %s, scraping_time = %s "
                  "WHERE id = %s;")

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        if records is None:
            cursor.execute(scrape_sql, ('0', message, scraping_time, scrape_id))
            connection.commit()
            return

        cursor.execute(scrape_sql, (len(records), message, scraping_time, scrape_id))
        connection.commit()


def save_records(records, scraper_settings, session_id):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        records = format_aliases(records, scraper_settings.domain)

        record_ids = get_record_ids(records, cursor)

        formatted_records = format_records(records, scraper_settings, session_id, record_ids)
        new_records, records_with_images = split_records(formatted_records, record_ids)

        save_new_records(cursor, new_records)
        update_record_images(cursor, records_with_images)

        update_prices(cursor, records, session_id)
        update_reappearing_records(cursor, scraper_settings.url, record_ids)
        update_sold_records(cursor, scraper_settings.url, record_ids)


def format_records(records, scraper_settings, session_id, record_ids):
    formatted_records = []
    records_with_images = ImageService.get_records_with_images(scraper_settings)

    start = timeit.default_timer()
    for record in records:
        if check_for_duplicates(record, formatted_records):
            continue

        if record.get('alias') in records_with_images and record.get('alias') in record_ids:
            continue

        record = handle_record_image(record)

        formatted_record = (record.get('alias'),
                             record.get('title'),
                             record.get('make'),
                             record.get('model'),
                             record.get('variant'),
                             record.get('year'),
                             record.get('mileage'),
                             format_link(record, scraper_settings.url),
                             session_id,
                             record.get('sharepoint_link'),
                             record.get('image_hash'),
                             record.get('fuel_type'),
                             record.get('transmission'),)
        formatted_records.append(formatted_record)
    logging.log(19, f"DB > Format records: {timeit.default_timer() - start:.3f}s")

    return formatted_records


def handle_record_image(record):
    record_image = record.get('record_image')

    if record_image is None:
        return record

    try:
        record['image_hash'] = record_image.hash
        record['sharepoint_link'] = record_image.save(record['alias'])
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(f"Error while trying to get image data: \n{traceback.format_exc()}")
    finally:
        return record


def split_records(formatted_records, record_ids):
    new_records = []
    existing_records = []

    start = timeit.default_timer()

    for formatted_record in formatted_records:
        if formatted_record[0] in record_ids:
            existing_records.append(formatted_record)
        else:
            new_records.append(formatted_record)

    logging.log(19, f"DB > Split records: {timeit.default_timer() - start:.3f}s")

    return new_records, existing_records


def format_link(record, url):
    if record['link'] is None:
        return None
    if record['link'].startswith('http') or record['link'].startswith('www'):
        return record['link']
    else:
        if url.endswith('/'):
            if record['link'].startswith('/'):
                return url[:-1] + record['link']
            return url + record['link']
        return f"{url}/{record['link']}"


# Should be unnecessary, but just in case
def check_for_duplicates(record, formatted_records):
    for formatted_record in formatted_records:
        if formatted_record[0] == record['alias']:
            return True
    return False


def update_prices(cursor, records, session_id):
    start = timeit.default_timer()
    prices_sql = ("INSERT INTO prices (record_id, price, scraping_session_id)"
                  "VALUES (%s, %s, %s);")

    formatted_prices = []
    try:
        for record in records:
            record_id = get_record_id(record, cursor)

            if record_id is None:
                continue

            formatted_price = (record_id,
                               record['price'],
                               session_id)
            formatted_prices.append(formatted_price)
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(traceback.format_exc())
        return
    finally:
        logging.log(19, f"DB > Format prices: {timeit.default_timer() - start:.3f}s")

    start = timeit.default_timer()

    cursor.executemany(prices_sql, formatted_prices)
    cursor.connection.commit()

    logging.log(logging.INFO, f"Saved {len(formatted_prices)} prices")
    logging.log(19, f"DB > Save prices: {timeit.default_timer() - start:.3f}s")


def update_sold_records(cursor, url, record_ids):
    if record_ids is None or len(record_ids) == 0:
        return

    start = timeit.default_timer()
    formatted_sold_records = []

    try:
        cursor.execute("SELECT records.id FROM records "
                       "JOIN scraping_sessions ON scraping_sessions.id = records.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NULL AND records.id NOT IN %s",
                       (url, tuple(record_ids.values()),))
        sold_records = cursor.fetchall()

        for sold_record in sold_records:
            formatted_sold_records.append((datetime.now() - timedelta(days=1), sold_record[0]))
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(traceback.format_exc())
        return []
    finally:
        logging.log(19, f"DB > Format sold records: {timeit.default_timer() - start:.3f}s")

    sold_record_sql = "UPDATE records SET date_sold = %s WHERE id = %s;"

    start = timeit.default_timer()

    cursor.executemany(sold_record_sql, formatted_sold_records)
    cursor.connection.commit()

    logging.log(19, f"DB > Update sold records: {timeit.default_timer() - start:.3f}s")
    logging.log(logging.INFO, f"Updated {len(formatted_sold_records)} sold records")


def update_reappearing_records(cursor, url, record_ids):
    if record_ids is None or len(record_ids) == 0:
        return

    sold_record_sql = "UPDATE records SET date_sold = %s WHERE id = %s;"

    start = timeit.default_timer()
    formatted_reappearing_records = []

    try:
        cursor.execute("SELECT records.id FROM records "
                       "JOIN scraping_sessions ON scraping_sessions.id = records.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NOT NULL AND records.id IN %s",
                       (url, tuple(record_ids.values()),))
        sold_reappearing_records = cursor.fetchall()

        for reappearing_record in sold_reappearing_records:
            formatted_reappearing_records.append((None, reappearing_record[0]))
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(traceback.format_exc())
        return
    finally:
        logging.log(19, f"DB > Format reappearing records: {timeit.default_timer() - start:.3f}s")

    start = timeit.default_timer()

    cursor.executemany(sold_record_sql, formatted_reappearing_records)
    cursor.connection.commit()

    logging.log(19, f"DB > Update reappearing records: {timeit.default_timer() - start:.3f}s")
    logging.log(logging.INFO, f"Updated {len(formatted_reappearing_records)} reappearing records")


def get_record_ids(records, cursor):
    start = timeit.default_timer()
    try:
        record_ids = {}

        if records is None or len(records) == 0:
            return record_ids

        cursor.execute("SELECT alias, id FROM records WHERE alias IN %s",
                       (tuple([record['alias'] for record in records]),))
        result = cursor.fetchall()

        for found_record in result:
            record_ids[found_record[0]] = found_record[1]

        return record_ids
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(traceback.format_exc())
        return []
    finally:
        logging.log(19, f"DB > Get record ids: {timeit.default_timer() - start:.3f}s")


def get_record_id(record, cursor):
    try:
        cursor.execute("SELECT id FROM records WHERE alias = %s", (record['alias'],))
        result = cursor.fetchall()

        if len(result) > 1:
            raise Exception(f"Multiple records with same alias: {record['alias']}")
        elif len(result) == 1:
            return result[0][0]
        else:
            return None
    except SystemExit or KeyboardInterrupt:
        exit(-1)
    except:
        logging.error(traceback.format_exc())
        return None


def update_record_images(cursor, records):
    record_update_sql = ("UPDATE records SET image_link = %s, image_hash = %s "
                          "WHERE alias = %s AND image_link IS NULL;")

    start = timeit.default_timer()
    for record in records:
        cursor.execute(record_update_sql, (record[9],
                                            record[10],
                                            record[0]))
    logging.info(f"Updated {len(records)} records")
    logging.log(19, f"DB > Update existing records: {timeit.default_timer() - start:.3f}s")


def format_aliases(records, domain):
    start = timeit.default_timer()

    for record in records:
        if record.get('alias') is None or record.get('alias') == '':
            continue
        record['alias'] = f"{domain}_{record['alias']}"

    logging.log(19, f"DB > Format alias: {timeit.default_timer() - start:.3f}s")
    return records


def save_new_records(cursor, new_records):
    record_sql = ("INSERT INTO records (alias, title, make, model, variant, year, mileage, link,"
                   "scraping_session_id, image_link, image_hash, fuel_type, transmission) "
                   "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);")

    start = timeit.default_timer()

    for record in new_records:
        try:
            cursor.execute(record_sql, record)
        except SystemExit or KeyboardInterrupt:
            exit(-1)
        except:
            logging.error(f"Error while saving record: {record}\n{traceback.format_exc()}")
    cursor.connection.commit()

    logging.info(f"Saved {len(new_records)} records")
    logging.log(19, f"DB > Save new records: {timeit.default_timer() - start:.3f}s")


def get_average_count(url: str):
    """
    Get the average record count in the last week for a given url. Discards runs that are not finished, have fewer
    records than the record count warning, are older than a week or newer than a day.
    :param url: The url to get the average record count for.
    :return: The average record count. If no average is found, None is returned.
    """
    record_count_warning = settings_service.get_catalog_setting('record_count_warning')

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute("""
        select avg(found_count) from scraping_sessions
        where url = %s
            and found_count > %s
            and run_id in (
                select id from runs 
                where end_time is not null
                                and end_time > current_date - interval '7 days'
                                and end_time < current_date - interval '1 day');
        """, (url,record_count_warning,))
        result = cursor.fetchone()

        if result is None or result[0] is None:
            logging.warning(f"No average found for {url}")
            return None

        return int(result[0])

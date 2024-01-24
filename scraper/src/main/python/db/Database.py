import logging
import timeit
import traceback
from datetime import datetime, timedelta

import psycopg2
from db import Credentials
from services import SettingsService

SettingsService = SettingsService.service


def connect():
    try:
        database = Credentials.DATABASE

        connection = psycopg2.connect(host=Credentials.SERVER,
                                      database=database,
                                      user=Credentials.USERNAME,
                                      password=Credentials.PASSWORD)
        return connection
    except psycopg2.Error as e:
        raise Exception("Error connecting to database: " + traceback.format_exc())


def get_cursor(connection):
    try:
        cursor = connection.cursor()
        return cursor
    except psycopg2.Error as e:
        raise Exception("Error getting cursor: " + traceback.format_exc())


def save_run():
    run_sql = "INSERT INTO runs (start_time, end_time) VALUES (DEFAULT, NULL) RETURNING id;"

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        cursor.execute(run_sql)
        connection.commit()
        run_id = cursor.fetchone()[0]

        return run_id
    finally:
        if connection is not None:
            connection.close()


def end_run(run_id):
    start_sql = "SELECT start_time FROM runs WHERE id = %s;"
    run_sql = "UPDATE runs SET end_time = %s, duration = %s WHERE id = %s;"

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        cursor.execute(start_sql, (run_id,))
        start_time = cursor.fetchone()[0]

        tz_info = start_time.tzinfo
        end_time = datetime.now(tz_info)

        cursor.execute(run_sql, (end_time, end_time - start_time, run_id,))

        logging.info(f"End time: {datetime.now()} Duration: {end_time - start_time}")

        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def save_scrape(domain, locale, url, records, message, scraping_time, run_id):
    scrape_sql = ("INSERT INTO scraping_sessions (domain, locale, url, found_count, result, scraping_time, run_id) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;")

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        if records is None:
            cursor.execute(scrape_sql, (domain, locale, url, '0', message, scraping_time, run_id))
        else:
            cursor.execute(scrape_sql, (domain, locale, url, len(records), message, scraping_time, run_id))

        connection.commit()
        scrape_id = cursor.fetchone()[0]

        return scrape_id
    finally:
        if connection is not None:
            connection.close()


def update_scrape(scrape_id, records, message, scraping_time):
    scrape_sql = ("UPDATE scraping_sessions SET found_count = %s, result = %s, scraping_time = %s "
                  "WHERE id = %s;")

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        if records is None:
            cursor.execute(scrape_sql, ('0', message, scraping_time, scrape_id))
            connection.commit()
            return

        cursor.execute(scrape_sql, (len(records), message, scraping_time, scrape_id))
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def save_records(records, url, session_id, domain):
    record_sql = ("INSERT INTO records (alias, title, make, model, variant, year, mileage, link, scraping_session_id)"
                   "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);")
    prices_sql = ("INSERT INTO prices (record_id, price, scraping_session_id)"
                  "VALUES (%s, %s, %s);")
    sold_record_sql = "UPDATE records SET date_sold = %s WHERE id = %s;"

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        start = timeit.default_timer()
        for record in records:
            record['alias'] = format_alias(record['alias'], domain)
        logging.log(19, f"DB > Format alias: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        formatted_records = format_records(records, session_id, cursor, url)
        logging.log(19, f"DB > Format records: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(record_sql, formatted_records)
        connection.commit()
        logging.log(19, f"DB > Save records: {timeit.default_timer() - start}")

        logging.info(f"Saved {len(formatted_records)} records")

        start = timeit.default_timer()
        record_ids = get_record_ids(records, cursor)
        logging.log(19, f"DB > Get record ids: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        formatted_prices = format_prices(records, session_id, cursor)
        logging.log(19, f"DB > Format prices: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(prices_sql, formatted_prices)
        connection.commit()
        logging.log(19, f"DB > Save prices: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Saved {len(formatted_prices)} prices")

        start = timeit.default_timer()
        reappearing_records = format_reappearing_records(url, cursor, record_ids)
        logging.log(19, f"DB > Format reappearing records: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(sold_record_sql, reappearing_records)
        connection.commit()
        logging.log(19, f"DB > Update reappearing records: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Updated {len(reappearing_records)} reappearing records")

        start = timeit.default_timer()
        sold_records = format_sold_records(url, cursor, record_ids)
        logging.log(19, f"DB > Format sold records: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(sold_record_sql, sold_records)
        connection.commit()
        logging.log(19, f"DB > Update sold records: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Updated {len(sold_records)} sold records")
    finally:
        if connection is not None:
            connection.close()


def format_records(records, session_id, cursor, url):
    formatted_records = []

    for record in records:
        if get_record_id(record, cursor) is not None:
            continue

        if check_for_duplicates(record, formatted_records):
            continue

        formatted_record = (record.get('alias'),
                             record.get('title'),
                             record.get('make'),
                             record.get('model'),
                             record.get('variant'),
                             record.get('year'),
                             record.get('mileage'),
                             format_link(record, url),
                             session_id)
        formatted_records.append(formatted_record)

    return formatted_records


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


def format_prices(records, session_id, cursor):
    try:
        formatted_prices = []

        for record in records:
            record_id = get_record_id(record, cursor)

            if record_id is None:
                continue

            formatted_price = (record_id,
                               record['price'],
                               session_id)
            formatted_prices.append(formatted_price)

        return formatted_prices
    except:
        logging.error(traceback.format_exc())
        return []


def format_sold_records(url, cursor, record_ids):
    try:
        cursor.execute("SELECT records.id FROM records "
                       "JOIN scraping_sessions ON scraping_sessions.id = records.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NULL AND records.id NOT IN %s", (url, tuple(record_ids),))
        sold_records = cursor.fetchall()

        formatted_sold_records = []

        for sold_record in sold_records:
            formatted_sold_records.append((datetime.now() - timedelta(days=1), sold_record[0]))

        return formatted_sold_records
    except:
        logging.error(traceback.format_exc())
        return []


def format_reappearing_records(url, cursor, record_ids):
    try:
        cursor.execute("SELECT records.id FROM records "
                       "JOIN scraping_sessions ON scraping_sessions.id = records.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NOT NULL AND records.id IN %s", (url, tuple(record_ids),))
        sold_reappearing_records = cursor.fetchall()

        formatted_reappearing_records = []

        for reappearing_record in sold_reappearing_records:
            formatted_reappearing_records.append((None, reappearing_record[0]))

        return formatted_reappearing_records
    except:
        logging.error(traceback.format_exc())
        return []


def get_record_ids(records, cursor):
    try:
        record_ids = []

        for record in records:
            record_id = get_record_id(record, cursor)
            if record_id is not None:
                record_ids.append(record_id)

        return record_ids
    except:
        logging.error(traceback.format_exc())
        return []


def get_record_id(record, cursor):
    try:
        cursor.execute("SELECT id FROM records WHERE alias = %s", (record['alias'],))
        result = cursor.fetchall()

        if len(result) > 1:
            raise Exception("Multiple records with same alias: " + record['alias'])
        elif len(result) == 1:
            return result[0][0]
        else:
            return None
    except:
        logging.error(traceback.format_exc())
        return None


def format_alias(alias, domain):
    return f"{domain}_{alias}"

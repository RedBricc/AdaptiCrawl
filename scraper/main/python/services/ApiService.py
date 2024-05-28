import json
import logging
import timeit
from datetime import datetime, timedelta
from enum import Enum

from db import DatabaseConnector
from services import SettingsService

settings_service = SettingsService.service


class RecordType(Enum):
    RECORDS = 'RECORDS'
    PRICES = 'PRICES'


class CacheScope(Enum):
    DAILY = 'DAILY'
    ALL = 'ALL'


def get_records(page: int, page_size: int | None, date: str = None, use_cache: bool = True):
    if use_cache is True:
        cache_data = find_cached_data(RecordType.RECORDS, date)
        if cache_data is not None:
            return get_page(page, page_size, cache_data)

    date_condition = ""
    if date is not None:
        date_condition = f" AND vd.date_created > '{date}' AND vd.date_created < '{date + ' 23:59:59'}'"

    records_sql = ("SELECT"
                    " v.id, v.make, v.model, v.variant, v.year, v.title, v.mileage, v.date_created, v.link, v.image_link, p.price,"
                    " ss.domain, ss.url,"
                    " vd.registration_number, vd.vin_number, vd.sdk,"
                    " vd.technical_inspection, vd.engine_size, vd.fuel_type, vd.engine_power_kw, vd.exterior_color, vd.current_location, vd.body_type, vd.transmission, vd.drive_type,"
                    " s.type, s.name, s.phone, s.email, s.address,"
                    " vd.year, vd.mileage, v.fuel_type, v.transmission"
                    " FROM runs as r"
                    " JOIN scraping_sessions as ss ON r.id = ss.run_id"
                    " JOIN records as v ON ss.id = v.scraping_session_id"
                    " JOIN record_details as vd ON v.id = record_id"
                    " LEFT JOIN public.sellers s on s.id = vd.seller_id"
                    " LEFT JOIN (SELECT *, ROW_NUMBER() OVER(PARTITION BY record_id ORDER BY date_created DESC) as rn FROM prices) p ON v.id = p.record_id"
                    f" WHERE r.scheduler_id = 'SOURCING' AND v.date_sold IS NULL AND p.rn = 1 {date_condition}"
                    " ORDER BY v.date_created")
    if page_size is not None:
        records_sql += f" LIMIT {page_size} OFFSET  {(page - 1) * page_size}"

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(records_sql)
        records = cursor.fetchall()

    formatted_records = format_records(records)

    return formatted_records


def get_prices(page: int, page_size: int | None, date: str = None, use_cache: bool = True):
    if use_cache is True:
        cache_data = find_cached_data(RecordType.PRICES, date)
        if cache_data is not None:
            return get_page(page, page_size, cache_data)

    price_table_sql = "LEFT JOIN prices p ON v.id = p.record_id WHERE v.date_sold IS NULL "
    if date is not None:
        price_table_sql = (" LEFT JOIN ("
                           "    SELECT *, ROW_NUMBER() OVER(PARTITION BY record_id ORDER BY date_created DESC) as rn"
                           f"    FROM prices WHERE date_created > '{date}' AND date_created < '{date + ' 23:59:59'}'"
                           ") p ON v.id = p.record_id"
                           " WHERE p.rn = 1 AND v.date_sold IS NULL ")

    prices_sql = ("SELECT v.id, p.price, p.date_created, v.link"
                  " FROM runs r"
                  " JOIN scraping_sessions ss ON r.id = ss.run_id"
                  " JOIN records v ON ss.id = v.scraping_session_id"
                  " JOIN record_details vd ON v.id = vd.record_id"
                  f" {price_table_sql}"
                  "AND r.scheduler_id = 'SOURCING'"
                  " ORDER BY v.id, v.date_created")
    if page_size is not None:
        prices_sql += f" LIMIT {page_size} OFFSET {(page - 1) * page_size}"

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(prices_sql)
        prices = cursor.fetchall()

    formatted_prices = format_prices(prices)

    return formatted_prices


def get_record_page_count(page_size, date=None):
    cache_data = find_cached_data(RecordType.RECORDS, date)
    if cache_data is not None:
        return len(cache_data) // page_size + (len(cache_data) % page_size > 0)

    record_sql = ("SELECT COUNT(runs.id) FROM runs"
                   " JOIN scraping_sessions ON runs.id = scraping_sessions.run_id"
                   " JOIN records ON scraping_sessions.id = records.scraping_session_id"
                   " JOIN record_details ON records.id = record_id"
                   " WHERE scheduler_id = 'SOURCING' AND date_sold IS NULL")
    if date is not None:
        record_sql += f" AND records.date_created > '{date}' AND records.date_created < '{date + ' 23:59:59'}'"

    return get_page_count(page_size, record_sql)


def get_price_page_count(page_size, date=None):
    cache_data = find_cached_data(RecordType.PRICES, date)
    if cache_data is not None:
        return len(cache_data) // page_size + (len(cache_data) % page_size > 0)

    price_sql = ("SELECT COUNT(DISTINCT record_id) FROM runs"
                 " JOIN scraping_sessions ON runs.id = scraping_sessions.run_id"
                 " JOIN records ON scraping_sessions.id = records.scraping_session_id"
                 " LEFT JOIN prices ON records.id = prices.record_id"
                 " WHERE scheduler_id = 'SOURCING' AND date_sold IS NULL")
    if date is not None:
        price_sql += f" AND prices.date_created > '{date}' AND prices.date_created < '{date + ' 23:59:59'}'"

    return get_page_count(page_size, price_sql)


def get_page_count(page_size, sql):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        record_count = cursor.fetchone()[0]

    return record_count // page_size + (record_count % page_size > 0)


def find_cached_data(record_type, date=None):
    """
    :return: The data from the cache for the given record type or None if no data is found
    """
    if date is None:
        cache_scope = CacheScope.ALL
    else:
        cache_scope = CacheScope.DAILY

    date_condition = ""
    if date is not None:
        date_condition = f" AND date = '{date}'"

    cache_sql = (f"SELECT data FROM api_cache WHERE cache_type = '{format_cache_scope(cache_scope, record_type)}'"
                 f" {date_condition}"
                 f" ORDER BY date DESC LIMIT 1")

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(cache_sql)
        data = cursor.fetchone()

    return data[0] if data is not None else None


def get_page(page, page_size, data):
    start_index = (page - 1) * page_size
    end_index = page * page_size

    return data[start_index:end_index]


def update_cache():
    """
    Updates the cache for the API
    """
    start = timeit.default_timer()
    logging.info("Updating cache...")

    cache_duration_days = settings_service.get_api_setting('cache_duration_days')

    # Delete old daily cache
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"DELETE FROM api_cache WHERE date < '{datetime.now().date() - timedelta(days=cache_duration_days)}'")
        connection.commit()

    # Update all time cache
    record_data = get_records(page=1, page_size=None, use_cache=False)
    execute_cache_update(record_data, format_cache_scope(CacheScope.ALL, RecordType.RECORDS))

    price_data = get_prices(page=1, page_size=None, use_cache=False)
    execute_cache_update(price_data, format_cache_scope(CacheScope.ALL, RecordType.PRICES))

    # Add daily cache for yesterday
    yesterday = (datetime.now().date() - timedelta(days=1)).strftime('%Y-%m-%d')

    record_data = get_records(page=1, page_size=None, date=yesterday, use_cache=False)
    execute_cache_insert(record_data, format_cache_scope(CacheScope.DAILY, RecordType.RECORDS), yesterday)

    price_data = get_prices(page=1, page_size=None, date=yesterday, use_cache=False)
    execute_cache_insert(price_data, format_cache_scope(CacheScope.DAILY, RecordType.PRICES), yesterday)

    logging.info(f"Cache updated! Time taken: {timeit.default_timer() - start:.3f}s")


def execute_cache_update(data, cache_type):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE api_cache SET data = %s WHERE cache_type = %s"
                       " RETURNING id",
                       (json.dumps(data), cache_type))
        cache_id = cursor.fetchone()

        if cache_id is None:
            cursor.execute("INSERT INTO api_cache (cache_type, data) VALUES (%s, %s)",
                           (cache_type, json.dumps(data)))

        connection.commit()


def execute_cache_insert(data, cache_type, date):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM api_cache WHERE cache_type = %s AND date = %s",
                       (cache_type, date))
        cache_id = cursor.fetchone()

        if cache_id is not None:
            cursor.execute("UPDATE api_cache SET data = %s WHERE id = %s",
                           (json.dumps(data), cache_id[0]))
        else:
            cursor.execute("INSERT INTO api_cache (cache_type, date, data) VALUES (%s, %s, %s)",
                           (cache_type, date, json.dumps(data)))
        connection.commit()


def format_records(records):
    formatted_records = []
    for record in records:
        formatted_records.append({
            "basic_info": {
                "id": record[0],
                "make": record[1],
                "model": record[2],
                "variant": record[3],
                "year": record[4] if record[4] != 0 else record[30],
                "title": record[5],
                "mileage": record[6] if record[6] != 0 else record[31],
                "first_seen": datetime.strftime(record[7], '%Y-%m-%d') if record[7] is not None else None,
                "link": record[8],
                "image": record[9],
                "latest_price": record[10]
            },
            "additional_info": {
                "source_information": {
                    "domain": record[11],
                    "source_link": record[12]
                },
                "identification_information": {
                    "registration_number": record[13],
                    "vin_number": record[14],
                    "sdk": record[15]
                },
                "technical_information": {
                    "technical_inspection_valid_until": record[16],
                    "engine_size": record[17],
                    "fuel_type": record[18] if record[18] is not None or record[18] != '' else record[32],
                    "engine_power_kw": record[19],
                    "exterior_color": record[20],
                    "current_location": record[21],
                    "body_type": record[22],
                    "transmission": record[23] if record[23] is not None or record[23] != '' else record[33],
                    "drive_type": record[24]
                },
                "seller_information": {
                    "seller_type": record[25],
                    "seller_name": record[26],
                    "seller_phone": record[27],
                    "seller_email": record[28],
                    "seller_address": record[29]
                }
            }
        })

    return formatted_records


def format_prices(prices):
    formatted_prices = []
    for price in prices:
        formatted_prices.append({
            "id": price[0],
            "price": price[1],
            "date": datetime.strftime(price[2], '%Y-%m-%d') if price[2] is not None else None,
            "link": price[3]
        })

    return formatted_prices


def format_cache_scope(cache_scope: CacheScope, record_type: RecordType):
    return f"{cache_scope.value}_{record_type.value}"


if __name__ == '__main__':
    update_cache()

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


def save_scrape(domain, locale, url, vehicles, message, scraping_time, run_id):
    scrape_sql = ("INSERT INTO scraping_sessions (domain, locale, url, found_count, result, scraping_time, run_id) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;")

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        if vehicles is None:
            cursor.execute(scrape_sql, (domain, locale, url, '0', message, scraping_time, run_id))
        else:
            cursor.execute(scrape_sql, (domain, locale, url, len(vehicles), message, scraping_time, run_id))

        connection.commit()
        scrape_id = cursor.fetchone()[0]

        return scrape_id
    finally:
        if connection is not None:
            connection.close()


def update_scrape(scrape_id, vehicles, message, scraping_time):
    scrape_sql = ("UPDATE scraping_sessions SET found_count = %s, result = %s, scraping_time = %s "
                  "WHERE id = %s;")

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        if vehicles is None:
            cursor.execute(scrape_sql, ('0', message, scraping_time, scrape_id))
            connection.commit()
            return

        cursor.execute(scrape_sql, (len(vehicles), message, scraping_time, scrape_id))
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def save_vehicles(vehicles, url, session_id, domain):
    vehicle_sql = ("INSERT INTO vehicles (alias, title, make, model, variant, year, mileage, link, scraping_session_id)"
                   "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);")
    prices_sql = ("INSERT INTO prices (vehicle_id, price, scraping_session_id)"
                  "VALUES (%s, %s, %s);")
    sold_vehicle_sql = "UPDATE vehicles SET date_sold = %s WHERE id = %s;"

    connection = None
    try:
        connection = connect()
        cursor = get_cursor(connection)

        start = timeit.default_timer()
        for vehicle in vehicles:
            vehicle['alias'] = format_alias(vehicle['alias'], domain)
        logging.log(19, f"DB > Format alias: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        formatted_vehicles = format_vehicles(vehicles, session_id, cursor, url)
        logging.log(19, f"DB > Format vehicles: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(vehicle_sql, formatted_vehicles)
        connection.commit()
        logging.log(19, f"DB > Save vehicles: {timeit.default_timer() - start}")

        logging.info(f"Saved {len(formatted_vehicles)} vehicles")

        start = timeit.default_timer()
        vehicle_ids = get_vehicle_ids(vehicles, cursor)
        logging.log(19, f"DB > Get vehicle ids: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        formatted_prices = format_prices(vehicles, session_id, cursor)
        logging.log(19, f"DB > Format prices: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(prices_sql, formatted_prices)
        connection.commit()
        logging.log(19, f"DB > Save prices: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Saved {len(formatted_prices)} prices")

        start = timeit.default_timer()
        reappearing_vehicles = format_reappearing_vehicles(url, cursor, vehicle_ids)
        logging.log(19, f"DB > Format reappearing vehicles: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(sold_vehicle_sql, reappearing_vehicles)
        connection.commit()
        logging.log(19, f"DB > Update reappearing vehicles: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Updated {len(reappearing_vehicles)} reappearing vehicles")

        start = timeit.default_timer()
        sold_vehicles = format_sold_vehicles(url, cursor, vehicle_ids)
        logging.log(19, f"DB > Format sold vehicles: {timeit.default_timer() - start}")

        start = timeit.default_timer()
        cursor.executemany(sold_vehicle_sql, sold_vehicles)
        connection.commit()
        logging.log(19, f"DB > Update sold vehicles: {timeit.default_timer() - start}")

        logging.log(logging.INFO, f"Updated {len(sold_vehicles)} sold vehicles")
    finally:
        if connection is not None:
            connection.close()


def format_vehicles(vehicles, session_id, cursor, url):
    formatted_vehicles = []

    for vehicle in vehicles:
        if get_vehicle_id(vehicle, cursor) is not None:
            continue

        if check_for_duplicates(vehicle, formatted_vehicles):
            continue

        formatted_vehicle = (vehicle.get('alias'),
                             vehicle.get('title'),
                             vehicle.get('make'),
                             vehicle.get('model'),
                             vehicle.get('variant'),
                             vehicle.get('year'),
                             vehicle.get('mileage'),
                             format_link(vehicle, url),
                             session_id)
        formatted_vehicles.append(formatted_vehicle)

    return formatted_vehicles


def format_link(vehicle, url):
    if vehicle['link'] is None:
        return None
    if vehicle['link'].startswith('http') or vehicle['link'].startswith('www'):
        return vehicle['link']
    else:
        if url.endswith('/'):
            if vehicle['link'].startswith('/'):
                return url[:-1] + vehicle['link']
            return url + vehicle['link']
        return f"{url}/{vehicle['link']}"


# Should be unnecessary, but just in case
def check_for_duplicates(vehicle, formatted_vehicles):
    for formatted_vehicle in formatted_vehicles:
        if formatted_vehicle[0] == vehicle['alias']:
            return True
    return False


def format_prices(vehicles, session_id, cursor):
    try:
        formatted_prices = []

        for vehicle in vehicles:
            vehicle_id = get_vehicle_id(vehicle, cursor)

            if vehicle_id is None:
                continue

            formatted_price = (vehicle_id,
                               vehicle['price'],
                               session_id)
            formatted_prices.append(formatted_price)

        return formatted_prices
    except:
        logging.error(traceback.format_exc())
        return []


def format_sold_vehicles(url, cursor, vehicle_ids):
    try:
        cursor.execute("SELECT vehicles.id FROM vehicles "
                       "JOIN scraping_sessions ON scraping_sessions.id = vehicles.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NULL AND vehicles.id NOT IN %s", (url, tuple(vehicle_ids),))
        sold_vehicles = cursor.fetchall()

        formatted_sold_vehicles = []

        for sold_vehicle in sold_vehicles:
            formatted_sold_vehicles.append((datetime.now() - timedelta(days=1), sold_vehicle[0]))

        return formatted_sold_vehicles
    except:
        logging.error(traceback.format_exc())
        return []


def format_reappearing_vehicles(url, cursor, vehicle_ids):
    try:
        cursor.execute("SELECT vehicles.id FROM vehicles "
                       "JOIN scraping_sessions ON scraping_sessions.id = vehicles.scraping_session_id "
                       "WHERE scraping_sessions.url = %s AND date_sold IS NOT NULL AND vehicles.id IN %s", (url, tuple(vehicle_ids),))
        sold_reappearing_vehicles = cursor.fetchall()

        formatted_reappearing_vehicles = []

        for reappearing_vehicle in sold_reappearing_vehicles:
            formatted_reappearing_vehicles.append((None, reappearing_vehicle[0]))

        return formatted_reappearing_vehicles
    except:
        logging.error(traceback.format_exc())
        return []


def get_vehicle_ids(vehicles, cursor):
    try:
        vehicle_ids = []

        for vehicle in vehicles:
            vehicle_id = get_vehicle_id(vehicle, cursor)
            if vehicle_id is not None:
                vehicle_ids.append(vehicle_id)

        return vehicle_ids
    except:
        logging.error(traceback.format_exc())
        return []


def get_vehicle_id(vehicle, cursor):
    try:
        cursor.execute("SELECT id FROM vehicles WHERE alias = %s", (vehicle['alias'],))
        result = cursor.fetchall()

        if len(result) > 1:
            raise Exception("Multiple vehicles with same alias: " + vehicle['alias'])
        elif len(result) == 1:
            return result[0][0]
        else:
            return None
    except:
        logging.error(traceback.format_exc())
        return None


def format_alias(alias, domain):
    return f"{domain}_{alias}"

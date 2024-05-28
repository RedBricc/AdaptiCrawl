from db import DatabaseConnector
from services import SettingsService
from scrapers.ScraperSettings import ScraperSettings, ScraperType

settings_service = SettingsService.service


def update_scrape(scrape_id, record, message, scraping_time):
    scrape_sql = ("UPDATE scraping_sessions SET found_count = %s, result = %s, scraping_time = %s "
                  "WHERE id = %s;")

    found_count = len(record) - count_empty_fields(record)

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()

        cursor.execute(scrape_sql, (found_count, message, scraping_time, scrape_id))
        connection.commit()


def count_empty_fields(record_block):
    empty_fields = 0
    for key, value in record_block.items():
        if key == 'unavailable':
            continue
        if value is None or value == '':
            empty_fields += 1
    return empty_fields


def get_priority_configurations(run_id):
    backlog_interval = settings_service.get_scheduler_setting('vdp_backlog_interval_days', default=2)

    target_sql = ("SELECT domain, locale, link, records.id, records.alias FROM runs"
                  " JOIN scraping_sessions ON runs.id = run_id"
                  " JOIN records ON scraping_sessions.id = scraping_session_id"
                  " LEFT JOIN record_details ON records.id = record_id"
                  " WHERE record_id IS NULL"
                  "     AND record_details.id IS NULL"
                  "     AND date_sold IS NULL"
                  f"    AND runs.scheduler_id = '{settings_service.scheduler_id}'"
                  f"    AND records.date_created > current_date - interval '{backlog_interval} days'"
                  " ORDER BY domain, records.date_created;")

    return get_scrapable_configurations(run_id, target_sql)


def get_competitor_backlog_configurations(run_id):
    target_sql = format_backlog_sql(platforms=False)

    return get_scrapable_configurations(run_id, target_sql)


def get_platform_backlog_configurations(run_id):
    target_sql = format_backlog_sql(platforms=True)

    return get_scrapable_configurations(run_id, target_sql)


def get_inconclusive_configurations(run_id):
    target_sql = ("SELECT domain, locale, link, records.id, records.alias FROM runs"
                  " JOIN scraping_sessions ON runs.id = run_id"
                  " JOIN records ON scraping_sessions.id = scraping_session_id"
                  " LEFT JOIN record_details ON records.id = record_id"
                  " WHERE record_details.id IS NOT NULL"
                  "     AND date_sold IS NULL"
                  f"    AND runs.scheduler_id = '{settings_service.scheduler_id}'"
                  "     AND record_details.vin_number IS NULL "
                  "     AND record_details.registration_number IS NULL"
                  "     AND record_details.sdk IS NULL"
                  " ORDER BY domain, record_details.date_updated;")

    return get_scrapable_configurations(run_id, target_sql)


def format_backlog_sql(platforms):
    backlog_interval = settings_service.get_scheduler_setting('vdp_backlog_interval_days', default=2)
    platform_domains = settings_service.get_scheduler_setting('platform_domains', default=[])

    platform_sql = ''
    if len(platform_domains) > 0:
        formatted_platforms = ', '.join(f'\'{domain}\'' for domain in platform_domains)
        platform_sql = f"AND domain {'' if platforms else 'NOT'} IN ({formatted_platforms})"

    target_sql = ("SELECT domain, locale, link, records.id, records.alias FROM runs"
                  " JOIN scraping_sessions ON runs.id = run_id"
                  " JOIN records ON scraping_sessions.id = scraping_session_id"
                  " LEFT JOIN record_details ON records.id = record_id"
                  " WHERE record_id IS NULL"
                  "     AND record_details.id IS NULL"
                  "     AND date_sold IS NULL"
                  f"    AND runs.scheduler_id = '{settings_service.scheduler_id}'"
                  f"    AND records.date_created <= current_date - interval '{backlog_interval} days'"
                  f"    {platform_sql}"
                  " ORDER BY domain, records.date_created;")

    return target_sql


def get_scrapable_configurations(run_id, target_sql):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(target_sql)
        records = cursor.fetchall()

    formatted_settings = {}
    proxy_index = 0

    for record in records:
        settings = ScraperSettings(
            scraper_type=ScraperType.VDP,
            domain=record[0],
            locale=record[1],
            url=record[2],
            configuration={'record_id': record[3], 'record_alias': record[4]},
            run_id=run_id
        )

        if settings.domain not in formatted_settings:
            formatted_settings[settings.domain] = []

        formatted_settings[settings.domain].append(settings)
        proxy_index += 1

    return formatted_settings


def save_or_update_record(record):
    save_sql = ("INSERT INTO record_details (record_id, seller_id, make, model, variant, year, title, mileage,"
                " registration_number, vin_number, sdk, technical_inspection, engine_size, fuel_type,"
                " engine_power_kw, exterior_color, current_location, body_type, transmission, drive_type)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (record_id) DO UPDATE SET"
                " make = EXCLUDED.make,"
                " model = EXCLUDED.model,"
                " variant = EXCLUDED.variant,"
                " year = EXCLUDED.year,"
                " title = EXCLUDED.title,"
                " mileage = EXCLUDED.mileage,"
                " registration_number = EXCLUDED.registration_number,"
                " vin_number = EXCLUDED.vin_number,"
                " sdk = EXCLUDED.sdk,"
                " technical_inspection = EXCLUDED.technical_inspection,"
                " engine_size = EXCLUDED.engine_size,"
                " fuel_type = EXCLUDED.fuel_type,"
                " engine_power_kw = EXCLUDED.engine_power_kw,"
                " exterior_color = EXCLUDED.exterior_color,"
                " current_location = EXCLUDED.current_location,"
                " body_type = EXCLUDED.body_type,"
                " transmission = EXCLUDED.transmission,"
                " drive_type = EXCLUDED.drive_type;")

    formatted_record = format_record(record)

    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute(save_sql, formatted_record)
        connection.commit()


def format_record(record):
    return (record.get('id'),
            record.get('seller_id'),
            record.get('make'),
            record.get('model'),
            record.get('variant'),
            record.get('year'),
            record.get('title'),
            record.get('mileage'),
            record.get('registration_number'),
            record.get('vin_number'),
            record.get('sdk'),
            record.get('technical_inspection'),
            record.get('engine_size'),
            record.get('fuel_type'),
            record.get('power'),
            record.get('color'),
            record.get('location'),
            record.get('body_type'),
            record.get('transmission'),
            record.get('drive_type'))

import logging

import schedule

from db import DatabaseConnector


class TableCacheService:
    """
    Service for caching tables that aren't expected to change often.
    """
    def __init__(self):
        self.table_cache = {}
        schedule.every(15).minutes.do(self.update_table_cache)

    def get_table_values(self, table_name):
        if table_name in self.table_cache:
            return self.table_cache[table_name]

        with DatabaseConnector.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {table_name} order by id;")
            data = cursor.fetchall()

        unpacked_data = []
        for row in data:
            # ignore id column
            if len(row) == 2:
                unpacked_data.append(row[1])
            else:
                unpacked_data.append(row[1:])

        self.table_cache[table_name] = unpacked_data

        return unpacked_data

    def update_table_cache(self):
        logging.info("Updating table cache...")
        for table in self.table_cache:
            self.table_cache[table] = self.get_table_values(table)


service = TableCacheService()

import traceback

import psycopg2

from db import Credentials


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

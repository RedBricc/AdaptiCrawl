from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from db import DatabaseConnector


def get_user(api_key_header: str = Security(APIKeyHeader(name="scraper-api-key"))):
    print(api_key_header)
    return get_user_from_api_key(api_key_header)


def get_user_from_api_key(api_key):
    with DatabaseConnector.connect() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, name FROM users WHERE api_key = %s", (api_key,))
        record = cursor.fetchone()

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        return User(record[0], record[1])


class User:
    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name

    def __str__(self):
        return f"{self.name} (ID: {self.id})"

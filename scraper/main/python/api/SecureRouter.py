import logging
import timeit
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from regex import regex

from api import Auth
from api.Auth import User
from services import ApiService, LoggingService

router = APIRouter()


LoggingService.setup_logger()


@router.get("/ping")
async def get_ping(user: User = Depends(Auth.get_user)):
    logging.info(f"User {user} pinged the API")
    return {
        "user": user.name,
        "message": "pong"
    }


@router.get("/records")
def get_records(date: str = None, page: int = 1, page_size: int = 100, user: User = Depends(Auth.get_user)):
    start_time = timeit.default_timer()
    validate_pagination(page, page_size, user)

    date_string = parse_date(date, user)

    record_data = ApiService.get_records(page, page_size, date_string)

    if page > 1 and len(record_data) == 0:
        logging.error(f"User {user} requested page {page} of records for date {date} with page size {page_size}, "
                      f"but no more records are available")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Page number too large. No more records available")

    logging.info(f"User {user} requested page {page} of records for date {date} with page size {page_size}. "
                 f"Time taken: {timeit.default_timer() - start_time}")
    return format_response("records", record_data)


@router.get("/records/page-count")
def get_records_page_count(date: str = None, page_size: int = 100, user: User = Depends(Auth.get_user)):
    start_time = timeit.default_timer()
    validate_pagination(1, page_size, user)

    date_string = parse_date(date, user)

    logging.info(f"User {user} requested the page count of records for date {date} with page size {page_size}."
                 f"Time taken: {timeit.default_timer() - start_time}")
    return ApiService.get_record_page_count(page_size, date_string)


@router.get("/prices")
def get_prices(date: str = None, page: int = 1, page_size: int = 100, user: User = Depends(Auth.get_user)):
    start_time = timeit.default_timer()
    validate_pagination(page, page_size, user)

    date_string = parse_date(date, user)

    price_data = ApiService.get_prices(page, page_size, date_string)

    if page > 1 and len(price_data) == 0:
        logging.error(f"User {user} requested page {page} of prices for date {date} with page size {page_size}, "
                      f"but no more prices are available")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Page number too large. No more prices available")

    logging.info(f"User {user} requested page {page} of prices for date {date} with page size {page_size}. "
                 f"Time taken: {timeit.default_timer() - start_time}")
    return format_response("prices", price_data)


@router.get("/prices/page-count")
def get_prices_page_count(date: str = None, page_size: int = 100, user: User = Depends(Auth.get_user)):
    start_time = timeit.default_timer()
    validate_pagination(1, page_size, user)

    date_string = parse_date(date, user)

    logging.info(f"User {user} requested the page count of prices for date {date} with page size {page_size}. "
                 f"Time taken: {timeit.default_timer() - start_time}")
    return ApiService.get_price_page_count(page_size, date_string)


def validate_pagination(page, page_size, user: User):
    if page < 1:
        logging.error(f"User {user} requested a page number lower than 1")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Page number can't be lower than 1")

    if page_size < 1:
        logging.error(f"User {user} requested a page size lower than 1")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Page size has to be at least 1")


def parse_date(input_date: str, user: User):
    if input_date is None:
        return None

    try:
        cleaned_date = regex.sub(r'[^0-9\-]', '', input_date)  # Remove all characters except numbers and dashes
        date = datetime.strptime(cleaned_date, '%Y-%m-%d')
    except ValueError:
        logging.error(f"User {user} provided an invalid date format: {input_date}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid date format, use YYYY-MM-DD")

    if date > datetime.today() - timedelta(days=1):
        logging.error(f"User {user} requested a date in the future: {date}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Latest date available is yesterday. Use a date before today")

    return date.strftime('%Y-%m-%d')


def format_response(label, data):
    return {
        label: data
    }

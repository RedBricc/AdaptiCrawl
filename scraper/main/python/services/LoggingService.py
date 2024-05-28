import logging
import sys
from datetime import datetime
from pathlib import Path

from services import SettingsService


settings_service = SettingsService.service


def setup_logger(timestamp=datetime.now(), dev_log_level=19):
    """
    Initializes the logging to the console and log file based on the environment.
    :param timestamp: The timestamp to use for the log file name.
    :param dev_log_level: The log level to use in development mode.
    """
    logging.addLevelName(19, "LONGO_DEBUG")
    logging.addLevelName(18, "DETAILED")

    time_format = "%Y-%m-%d %H:%M:%S"
    formatted_date = timestamp.strftime('%Y-%m-%d_%H-%M')
    local_path = f"../../../../logs/{settings_service.scheduler_id}_{formatted_date}.log"
    file_string = str(Path(__file__).parent.joinpath(local_path).resolve())
    log_format = '%(asctime)s P[%(process)-5d] %(levelname)-11s %(message)s'

    logging.getLogger().handlers = []

    if settings_service.is_prod():
        configure_logging(file_string, log_format, logging.WARN, time_format)
    elif settings_service.is_stage():
        configure_logging(file_string, log_format, logging.INFO, time_format)
    else:
        configure_logging(file_string, log_format, dev_log_level, time_format)

    logging.info(f"Logging for {sys.argv[1]} initialized! [Running in {settings_service.get_env()} mode]")


def configure_logging(file_string, log_format, level, time_format):
    logging.basicConfig(filename=file_string, format=log_format, level=level, datefmt=time_format)

    console_logger_info = logging.StreamHandler(sys.stdout)
    console_logger_info.setLevel(level)
    console_logger_info.setFormatter(logging.Formatter(log_format))
    console_logger_info.addFilter(lambda record: record.levelno < logging.ERROR)

    logging.getLogger().addHandler(console_logger_info)

    console_logger_error = logging.StreamHandler(sys.stderr)
    console_logger_error.setLevel(logging.ERROR)
    console_logger_error.setFormatter(logging.Formatter(log_format))

    logging.getLogger().addHandler(console_logger_error)

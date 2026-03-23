import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = "tweet_bot",
    log_dir: str = "logs",
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Create and return a logger with console + rotating file output."""
    os.makedirs(log_dir, exist_ok=True)

    _logger = logging.getLogger(name)

    if _logger.handlers:
        return _logger

    _logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, f"{name}.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(name)s.%(funcName)s:%(lineno)d] %(levelname)s: %(message)s"
        )
    )

    _logger.addHandler(console)
    _logger.addHandler(file_handler)
    return _logger


logger = setup_logger(log_level=os.getenv("LOG_LEVEL", "INFO"))

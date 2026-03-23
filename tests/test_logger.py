"""Tests for tweet_tracker.logger module."""

import os
import logging
import tempfile
import importlib


def test_setup_logger_creates_logger():
    """setup_logger should return a properly configured logger."""
    from tweet_tracker.logger import setup_logger

    with tempfile.TemporaryDirectory() as tmpdir:
        lg = setup_logger(name="test_logger_1", log_dir=tmpdir, log_level="DEBUG")
        assert isinstance(lg, logging.Logger)
        assert lg.level == logging.DEBUG
        assert len(lg.handlers) == 2  # console + file


def test_setup_logger_creates_log_dir():
    """setup_logger should create the log directory if it doesn't exist."""
    from tweet_tracker.logger import setup_logger

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = os.path.join(tmpdir, "nested", "logs")
        setup_logger(name="test_logger_2", log_dir=log_dir)
        assert os.path.isdir(log_dir)


def test_setup_logger_no_duplicate_handlers():
    """Calling setup_logger twice with same name should not add duplicate handlers."""
    from tweet_tracker.logger import setup_logger

    with tempfile.TemporaryDirectory() as tmpdir:
        lg1 = setup_logger(name="test_logger_3", log_dir=tmpdir)
        handler_count = len(lg1.handlers)
        lg2 = setup_logger(name="test_logger_3", log_dir=tmpdir)
        assert lg1 is lg2
        assert len(lg2.handlers) == handler_count


def test_logger_writes_to_file():
    """Logger should write messages to the log file."""
    from tweet_tracker.logger import setup_logger

    with tempfile.TemporaryDirectory() as tmpdir:
        lg = setup_logger(name="test_logger_4", log_dir=tmpdir, log_level="INFO")
        lg.info("test message 12345")

        # Flush handlers
        for h in lg.handlers:
            h.flush()

        log_file = os.path.join(tmpdir, "test_logger_4.log")
        assert os.path.exists(log_file)
        content = open(log_file).read()
        assert "test message 12345" in content


def test_global_logger_exists():
    """Module-level logger should be available for import."""
    from tweet_tracker.logger import logger
    assert isinstance(logger, logging.Logger)
    assert logger.name == "tweet_bot"

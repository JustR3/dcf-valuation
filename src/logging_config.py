"""Structured logging framework for DCF Valuation Toolkit.

Provides consistent logging across all modules with:
- Configurable log levels
- File and console output
- Structured JSON logging option
- Performance timing decorators

Usage:
    from src.logging_config import get_logger, log_performance
    
    logger = get_logger(__name__)
    logger.info("Starting DCF calculation", ticker="AAPL")
    
    @log_performance
    def slow_function():
        ...
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Log levels from environment or default to INFO
LOG_LEVEL = os.getenv("DCF_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("DCF_LOG_FILE", "")  # Empty = no file logging
LOG_FORMAT = os.getenv("DCF_LOG_FORMAT", "text")  # "text" or "json"

# Create logs directory if file logging enabled
if LOG_FILE:
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


class DCFFormatter(logging.Formatter):
    """Custom formatter with colored output for console."""
    
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors and sys.stdout.isatty()
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
    
    def format(self, record: logging.LogRecord) -> str:
        # Add extra fields to message if present
        if hasattr(record, 'extra_fields') and record.extra_fields:
            extra = " | ".join(f"{k}={v}" for k, v in record.extra_fields.items())
            record.msg = f"{record.msg} | {extra}"
        
        formatted = super().format(record)
        
        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            return f"{color}{formatted}{self.RESET}"
        return formatted


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, 'extra_fields') and record.extra_fields:
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


class DCFLogger(logging.Logger):
    """Extended logger with structured field support."""
    
    def _log_with_fields(self, level: int, msg: str, fields: dict[str, Any] | None = None, **kwargs) -> None:
        """Log with optional structured fields."""
        extra = kwargs.pop('extra', {})
        extra['extra_fields'] = fields or {}
        super()._log(level, msg, args=(), extra=extra, **kwargs)
    
    def debug(self, msg: str, **fields) -> None:
        self._log_with_fields(logging.DEBUG, msg, fields)
    
    def info(self, msg: str, **fields) -> None:
        self._log_with_fields(logging.INFO, msg, fields)
    
    def warning(self, msg: str, **fields) -> None:
        self._log_with_fields(logging.WARNING, msg, fields)
    
    def error(self, msg: str, **fields) -> None:
        self._log_with_fields(logging.ERROR, msg, fields)
    
    def critical(self, msg: str, **fields) -> None:
        self._log_with_fields(logging.CRITICAL, msg, fields)


# Register custom logger class
logging.setLoggerClass(DCFLogger)


def get_logger(name: str) -> DCFLogger:
    """Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured DCFLogger instance
        
    Example:
        logger = get_logger(__name__)
        logger.info("Fetching data", ticker="AAPL", source="yfinance")
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        
        if LOG_FORMAT == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(DCFFormatter(use_colors=True))
        
        logger.addHandler(console_handler)
        
        # File handler (if configured)
        if LOG_FILE:
            file_handler = logging.FileHandler(LOG_FILE)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(JSONFormatter())  # Always JSON for files
            logger.addHandler(file_handler)
        
        # Don't propagate to root logger
        logger.propagate = False
    
    return logger


def log_performance(func: Callable | None = None, *, level: str = "DEBUG") -> Callable:
    """Decorator to log function execution time.
    
    Args:
        func: Function to decorate
        level: Log level for timing message
        
    Example:
        @log_performance
        def slow_function():
            time.sleep(1)
        
        @log_performance(level="INFO")
        def important_function():
            ...
    """
    def decorator(f: Callable) -> Callable:
        logger = get_logger(f.__module__)
        log_method = getattr(logger, level.lower(), logger.debug)
        
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = f(*args, **kwargs)
                elapsed = time.perf_counter() - start
                log_method(
                    f"{f.__name__} completed",
                    elapsed_ms=round(elapsed * 1000, 2),
                    status="success"
                )
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(
                    f"{f.__name__} failed",
                    elapsed_ms=round(elapsed * 1000, 2),
                    error=str(e),
                    status="error"
                )
                raise
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


class Timer:
    """Context manager for timing code blocks.
    
    Example:
        with Timer("DCF calculation"):
            result = engine.get_intrinsic_value()
        # Logs: "DCF calculation completed | elapsed_ms=123.45"
    """
    
    def __init__(self, name: str, logger: DCFLogger | None = None, level: str = "DEBUG"):
        self.name = name
        self.logger = logger or get_logger(__name__)
        self.level = level
        self.start: float = 0
        self.elapsed: float = 0
    
    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.elapsed = time.perf_counter() - self.start
        log_method = getattr(self.logger, self.level.lower(), self.logger.debug)
        
        if exc_type is None:
            log_method(f"{self.name} completed", elapsed_ms=round(self.elapsed * 1000, 2))
        else:
            self.logger.error(
                f"{self.name} failed",
                elapsed_ms=round(self.elapsed * 1000, 2),
                error=str(exc_val)
            )


# Silence noisy third-party loggers
def configure_third_party_loggers() -> None:
    """Configure third-party library loggers to reduce noise."""
    noisy_loggers = [
        "urllib3",
        "requests",
        "yfinance",
        "peewee",
        "httpx",
        "httpcore",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


# Auto-configure on import
configure_third_party_loggers()

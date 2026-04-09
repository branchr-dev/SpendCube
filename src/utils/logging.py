"""SpendCube structured logging configuration."""

# NOTE: This file is intentionally named logging.py per the project spec.
# Python adds the script's directory to sys.path[0] when run directly, which
# causes `import logging` to resolve to *this* file instead of the stdlib.
# The block below removes our own directory from the front of sys.path for
# the duration of the stdlib import, then restores it.
import os as _os
import sys as _sys

_this_dir = _os.path.dirname(_os.path.abspath(__file__))
_shadowed = [i for i, p in enumerate(_sys.path)
             if _os.path.abspath(p or _os.getcwd()) == _this_dir]
for _i in reversed(_shadowed):
    _sys.path.pop(_i)

import logging  # noqa: E402 — must come after sys.path fixup

for _i, _p in zip(_shadowed, [_this_dir] * len(_shadowed)):
    _sys.path.insert(_i, _p)

import json
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any extra fields attached to the record (e.g. from log_llm_call).
        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _skip:
                payload[key] = value
        return json.dumps(payload, default=str)


def get_logger(name: str, level: str = "INFO", json_format: bool = False) -> logging.Logger:
    """Return a configured logger.

    Args:
        name: Logger name (usually __name__ of the calling module).
        level: Logging level string, e.g. 'DEBUG', 'INFO', 'WARNING'.
        json_format: When True emit JSON lines; when False emit human-readable text.

    Returns:
        A stdlib Logger with a single StreamHandler writing to stdout.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers when get_logger is called multiple times.
    if logger.handlers:
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    if json_format:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_llm_call(
    logger: logging.Logger,
    prompt: str,
    response: str,
    model: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Log a single LLM call at INFO level with structured metadata.

    Args:
        logger: Logger instance to write to.
        prompt: Full prompt text sent to the model.
        response: Full response text received from the model.
        model: Model identifier string.
        tokens_used: Total tokens consumed by this call.
        cost_usd: Estimated cost in USD for this call.
    """
    logger.info(
        "LLM call completed",
        extra={
            "llm_call": True,
            "model": model,
            "tokens_used": tokens_used,
            "cost_usd": cost_usd,
            "prompt_preview": prompt[:100],
        },
    )


def get_logger_from_config(name: str, config) -> logging.Logger:
    """Construct a logger from a config object.

    Reads ``config.logging.level`` (default ``'INFO'``) and
    ``config.logging.json_format`` (default ``False``).  The config object
    may be a plain namespace, a dataclass, a Pydantic model, or any object
    with attribute access.  Dict-style configs are also supported.

    Args:
        name: Logger name.
        config: Configuration object with logging settings.

    Returns:
        Configured Logger instance.
    """

    def _get(obj, *keys, default=None):
        for key in keys:
            try:
                obj = getattr(obj, key)
            except AttributeError:
                try:
                    obj = obj[key]
                except (KeyError, TypeError):
                    return default
        return obj

    level = _get(config, "logging", "level", default="INFO")
    json_format = _get(config, "logging", "json_format", default=False)
    return get_logger(name, level=str(level), json_format=bool(json_format))


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Human-readable format ===")
    log = get_logger("demo", level="DEBUG", json_format=False)
    log.info("Application started")
    log.warning("Low disk space detected")
    log.error("Failed to connect to database")

    print("\n=== JSON format ===")
    jlog = get_logger("demo.json", level="DEBUG", json_format=True)
    jlog.info("Application started")
    jlog.warning("Low disk space detected")
    jlog.error("Failed to connect to database")

    print("\n=== LLM call logging (JSON) ===")
    llm_log = get_logger("demo.llm", level="DEBUG", json_format=True)
    log_llm_call(
        llm_log,
        prompt="Classify the following supplier name into a UNSPSC category: Officeworks",
        response="72151501",
        model="claude-sonnet-4-20250514",
        tokens_used=312,
        cost_usd=0.0023,
    )

    print("\n=== get_logger_from_config ===")

    class _LoggingCfg:
        level = "WARNING"
        json_format = False

    class _Cfg:
        logging = _LoggingCfg()

    cfg_log = get_logger_from_config("demo.cfg", _Cfg())
    cfg_log.info("This INFO message should NOT appear (level=WARNING)")
    cfg_log.warning("This WARNING message SHOULD appear")

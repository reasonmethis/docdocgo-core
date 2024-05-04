import atexit
import datetime as dt
import json
import logging
import logging.config
import logging.handlers
import pathlib
from logging.config import ConvertingDict, ConvertingList, valid_ident
from logging.handlers import QueueHandler, QueueListener
from queue import Queue

from utils.filesystem import ensure_path_exists

# from typing import override

LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


# https://github.com/mCodingLLC/VideosSampleCode/blob/master/videos/135_modern_logging/mylogger.py
class MyJSONFormatter(logging.Formatter):
    def __init__(
        self,
        *,
        fmt_keys: dict[str, str] | None = None,
    ):
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    # @override
    def format(self, record: logging.LogRecord) -> str:
        message = self._prepare_log_dict(record)
        return json.dumps(message, default=str)

    def _prepare_log_dict(self, record: logging.LogRecord):
        always_fields = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(
                record.created, tz=dt.timezone.utc
            ).isoformat(),
        }
        if record.exc_info is not None:
            always_fields["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info is not None:
            always_fields["stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: msg_val
            if (msg_val := always_fields.pop(val, None)) is not None
            else getattr(record, val)
            for key, val in self.fmt_keys.items()
        }
        message.update(always_fields)

        for key, val in record.__dict__.items():
            if key not in LOG_RECORD_BUILTIN_ATTRS:
                message[key] = val

        return message


class NonErrorFilter(logging.Filter):
    # @override
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return record.levelno <= logging.INFO


# https://rob-blackbourn.medium.com/how-to-use-python-logging-queuehandler-with-dictconfig-1e8b1284e27a
def _resolve_handlers(h):
    """Converts a list of handlers specified in a JSON file to actual handler objects."""
    if isinstance(h, ConvertingList):
        # Getting each item converts it to an actual object
        h = [h[i] for i in range(len(h))]
    return h


def _resolve_convertingdict(q):
    """Resolves a dict specified in a JSON file to an actual object, if necessary."""
    if not isinstance(q, ConvertingDict):
        return q
    if "__resolved_value__" in q:
        return q["__resolved_value__"]

    cname = q.pop("class")
    klass = q.configurator.resolve(cname)
    props = q.pop(".", None)
    kwargs = {k: q[k] for k in q if valid_ident(k)}
    result = klass(**kwargs)
    if props:
        for name, value in props.items():
            setattr(result, name, value)

    q["__resolved_value__"] = result
    return result


class QueueListenerHandler(QueueHandler):
    def __init__(
        self, handlers, respect_handler_level=False, auto_run=True, queue=Queue(0)
    ):
        queue = _resolve_convertingdict(queue)
        super().__init__(queue)
        handlers = _resolve_handlers(handlers)
        self._listener = QueueListener(
            self.queue, *handlers, respect_handler_level=respect_handler_level
        )
        if auto_run:
            self.start()
            atexit.register(self.stop)

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()

    def emit(self, record):  # NOTE: remove?
        return super().emit(record)


def setup_logging(log_level: str | None, log_format: str | None):
    ensure_path_exists("logs/ddg-logs.jsonl")
    with open(pathlib.Path("config/logging.json")) as f:
        config = json.load(f)
        if log_format:
            config["formatters"]["custom"] = {
                "format": log_format,
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            }
            config["handlers"]["h1_stderr"]["formatter"] = "custom"

        if log_level:
            config["handlers"]["h1_stderr"]["level"] = log_level
    
    logging.config.dictConfig(config)

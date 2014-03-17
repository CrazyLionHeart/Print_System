#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

SENTRY_DSN = "http://475ae49ccd5a4edc8df4ce80cb6135f2:1107ae1c79574e0790c3afe2cf58265f@sentry.bbp/2"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "simple": {
            "format": "%(levelname)s %(message)s",
            "datefmt": "%y %b %d, %H:%M:%S",
        },
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
            "datefmt": "%y %b %d, %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple"
        },
        "sentry": {
            "level": "WARNING",
            "class": "raven.handlers.logging.SentryHandler",
            "dsn": SENTRY_DSN,
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/print_system.log",
            "maxBytes": 1000000,
            "formatter": "verbose",
            "backupCount": 5
        }
    },
    "loggers": {
        "": {
            "handlers": ["console", "sentry", "file"],
            "level": "DEBUG",
            "propagate": True,
        },
        "activemq": {
            "handlers": ["console", "sentry"],
            "level": "WARN",
            "propagate": True,
        }
    }
}

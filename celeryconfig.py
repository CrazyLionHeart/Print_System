#!/usr/bin/env python
# -*- coding: utf-8 -*-

BROKER_URL = 'amqp://guest:guest@localhost:5672//'
CELERY_RESULT_BACKEND = 'amqp://guest:guest@localhost:5672//'
CELERY_IMPORTS = ("tasks", )
CELERY_TASK_RESULT_EXPIRES = 300
CELERY_TIMEZONE = 'Europe/Moscow'
CELERY_ENABLE_UTC = True
CELERY_SEND_TASK_ERROR_EMAILS = True
CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']

# Name and email addresses of recipients
ADMINS = (
    ("Administrators", "it_babypages_K52@babypages.ru"),
)

# Email address used as sender (From field).
SERVER_EMAIL = "robot@babypages.ru"

# Mailserver configuration
EMAIL_HOST = "localhost"
EMAIL_PORT = 25

#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import

try:
    import logging
    from logging.config import dictConfig
    from loggingconfig import LOGGING

    from celery import Celery
    from celery.utils.log import get_task_logger
    import celeryconfig

except Exception, e:
    raise e

celery = Celery()
celery.config_from_object(celeryconfig)

current_env = environ.get("APPLICATION_ENV", 'development')

with open('../../config/%s/config.%s.json' % (current_env, current_env)) as f:
    config = json.load(f)
    dictConfig(config['loggingconfig'])

logger = get_task_logger('celery')


@celery.task
def hello():
    return 'hello world'

@celery.task
def add(x, y):
    return x + y

if __name__ == "__main__":
    celery.start()

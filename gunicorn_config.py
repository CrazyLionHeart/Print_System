#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os import environ
import json

current_env = environ.get("APPLICATION_ENV", 'development')

with open('./config/%s/config.%s.json' % (current_env, current_env)) as f:
    config = json.load(f)

    bind = '%s:%s' % (config["gunicorn"]["hostname"],
                      int(config["gunicorn"]["port"]))
    workers = int(config["gunicorn"]["workers"])
    worker_class = config["gunicorn"]["worker_class"]
    worker_connections = int(config["gunicorn"]["worker_connections"])
    timeout = int(config["gunicorn"]["timeout"])
    keepalive = int(config["gunicorn"]["keepalive"])

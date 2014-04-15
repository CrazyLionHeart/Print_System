#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os import environ
import json

current_env = environ.get("APPLICATION_ENV", 'development')

with open('./config/%s/config.%s.json' % (current_env, current_env)) as f:
    own_config = json.load(f)

gunicorn = own_config['gunicorn']

bind = '%s:%s' % (gunicorn["hostname"],
                  int(gunicorn["port"]))
workers = int(gunicorn["workers"])
worker_class = gunicorn["worker_class"]
worker_connections = int(gunicorn["worker_connections"])
timeout = int(gunicorn["timeout"])
keepalive = int(gunicorn["keepalive"])
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import app
from os import environ
import json

current_env = environ.get("APPLICATION_ENV", 'development')

with open('config/%s/config.%s.json' % (current_env, current_env)) as f:
    config = json.load(f)

try:
    port = int(config["Print_System"]["port"])
    host = config["Print_System"]["hostname"]
    app.run(host=host, port=port)
except KeyboardInterrupt:
        pass

#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from flask import Flask, jsonify
from werkzeug.exceptions import default_exceptions
from werkzeug.exceptions import HTTPException

try:
    from raven.contrib.flask import Sentry
except ImportError, e:
    raise e

try:
    from os import environ
    import json
except ImportError, e:
    raise e

current_env = environ.get("APPLICATION_ENV", 'development')

with open('../../config/%s/config.%s.json' % (current_env, current_env)) as f:
    config = json.load(f)

sentry = Sentry(dsn=config['Raven']['dsn'])


__all__ = ['make_json_app']

def make_json_app(import_name, **kwargs):
    """
    Creates a JSON-oriented Flask app.

    All error responses that you don't specifically
    manage yourself will have application/json content
    type, and will contain JSON like this (just an example):

    { "message": "405: Method Not Allowed" }
    """
    def make_json_error(ex):
        response = jsonify(message=str(ex))
        response.status_code = (ex.code
                                if isinstance(ex, HTTPException)
                                else 500)
        return response

    app = Flask(import_name, **kwargs)
    sentry.init_app(app)


    for code in default_exceptions.iterkeys():
        app.error_handler_spec[None][code] = make_json_error

    return app

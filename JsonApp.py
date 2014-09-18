#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from flask import Flask, jsonify
    from werkzeug.exceptions import default_exceptions
    from werkzeug.exceptions import HTTPException

    from raven.contrib.flask import Sentry

    from os import environ
    import json
except ImportError, e:
    raise e

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

    current_env = environ.get("APPLICATION_ENV", 'development')

    with open('./config/%s/config.%s.json' % (current_env, current_env)) as f:
        config = json.load(f)

    dsn = "http://%s:%s@%s" % (config['Raven']['public'],
                               config['Raven']['private'],
                               config['Raven']['host'])

    app = Flask(import_name, **kwargs)
    app.config['SENTRY_DSN'] = dsn
    sentry = Sentry(app)

    for code in default_exceptions.iterkeys():
        app.error_handler_spec[None][code] = make_json_error

    return app

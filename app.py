#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from JsonApp import make_json_app
    import json

    import logging
    from logging.config import dictConfig

    from lxml import etree

    import requests

    from flask import jsonify, request, Response, make_response
    from flask import current_app, url_for
    from datetime import timedelta
    from Print_System import Print_System
    from functools import update_wrapper

    from .File_Storage.tasks import storage_put

    from os import environ
except Exception, e:
    raise e

current_env = environ.get("APPLICATION_ENV", 'development')

with open('../../config/%s/config.%s.json' % (current_env, current_env)) as f:
    config = json.load(f)
    dictConfig(config['loggingconfig'])

logger = logging.getLogger('print_system')

PS = Print_System(config)


def crossdomain(origin=None, methods=None, headers=None,
                max_age=21600, attach_to_all=True,
                automatic_options=True):
    if methods is not None:
        methods = ', '.join(sorted(x.upper() for x in methods))
    if headers is not None and not isinstance(headers, basestring):
        headers = ', '.join(x.upper() for x in headers)
    if not isinstance(origin, basestring):
        origin = ', '.join(origin)
    if isinstance(max_age, timedelta):
        max_age = max_age.total_seconds()

    def get_methods():
        if methods is not None:
            return methods

        options_resp = current_app.make_default_options_response()
        return options_resp.headers['allow']

    def decorator(f):
        def wrapped_function(*args, **kwargs):
            if automatic_options and request.method == 'OPTIONS':
                resp = current_app.make_default_options_response()
            else:
                resp = make_response(f(*args, **kwargs))
            if not attach_to_all and request.method != 'OPTIONS':
                return resp

            h = resp.headers

            h['Access-Control-Allow-Origin'] = origin
            h['Access-Control-Allow-Methods'] = get_methods()
            h['Access-Control-Max-Age'] = str(max_age)
            if headers is not None:
                h['Access-Control-Allow-Headers'] = headers
            return resp

        f.provide_automatic_options = False
        return update_wrapper(wrapped_function, f)
    return decorator

app = make_json_app(__name__)
# app.debug = True


@app.route('/')
@crossdomain(origin='*')
def example():
    """Помощь по API"""

    import urllib
    links = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            options = {}
            for arg in rule.arguments:
                options[arg] = "[{0}]".format(arg)

            methods = ','.join(rule.methods)

            url = url_for(rule.endpoint, **options)
            docstring = app.view_functions[rule.endpoint].__doc__
            links.append(
                dict(methods=methods, url=urllib.unquote(url),
                     docstring=docstring))

    return jsonify(results=links)


@app.route('/print', methods=['POST'])
@crossdomain(origin='*')
def print_xml():
    """Принимает файл на генерацию"""
    xmlObject = request.files.get('xml')

    config = {}

    if xmlObject:
        fileObject = xmlObject.read()

        xml = etree.fromstring(fileObject)

        count_elements = etree.XPath("count(//*[local-name() = $name])")

        if (count_elements(xml, name="print_data") != 1.0):
            raise Exception("No print_data")

        if (count_elements(xml, name="control_data") != 1.0):
            raise Exception("No control_data")
        else:
            control_data = xml.xpath('//control_data')[0]

        XML_URL = config['XML_URL']

        for child in control_data:
            config[child.tag] = child.text

        guid = config['XML_GET_PARAM_guid']

        if (PS.save_xml(guid, fileObject)):
            try:
                payload = dict(_flowId="viewReportFlow",
                               reportUnit=config['reportUnit'],
                               output=config['output'],
                               reportLocale="UTF-8",
                               j_username=config['JasperServer']['username'],
                               j_password=config["JasperServer"]["password"],
                               XML_GET_PARAM_guid=guid,
                               XML_URL=XML_URL)
                auth = requests.auth.HTTPBasicAuth(
                    'jasperadmin', 'jasperadmin')
                r = requests.get(
                    url='http://%s:%d/jasperserver/flow.html' %
                    (config['JasperServer']['hostname'],
                     config['JasperServer']['port']),
                    auth=auth, params=payload)
                if (PS.save_pdf(guid, r.content)):
                    if (config['print_type'] == 'print'):
                        result = PS.print_pdf(guid)
                        return jsonify(results=result)
                    else:
                        pdf = PS.get_pdf(guid)
                        database = "print_system"
                        content_type = 'application/pdf'

                        res = storage_put.apply_async((pdf, content_type, None,
                                                      database))
                        while (not res.ready()):
                            retval = res.get()
                            return jsonify(results=retval, state=res.state)

            except requests.exceptions.HTTPError as detail:
                raise Exception(
                    "Не могу получить сгенерированную печатную форму: %s" %
                    detail)
        else:
            raise Exception("Не удалось сохранить файл в хранилище.")
    else:
        raise Exception("No data in xml param")


@app.route('/get_preview', methods=['GET'])
@crossdomain(origin='*')
def get_preview():
    guid = request.args.get("guid")
    if guid:
        pdf = Print_System().get_pdf(guid)
        return Response(pdf, direct_passthrough=True,
                        mimetype='application/pdf')
    else:
        raise Exception("No guid param")


@app.route('/get_jrxml', methods=['GET'])
@crossdomain(origin='*')
def get_jrxml():
    guid = request.args.get('guid')
    if guid:
        xml = Print_System().get_xml(guid)
        print_data = etree.tostring(
            xml.xpath('//print_data')[0], encoding='utf-8', pretty_print=True)
        return Response(print_data, direct_passthrough=True,
                        mimetype='application/xml')


@app.route('/test', methods=['POST'])
@crossdomain(origin='*')
def test():

    xmlObject = request.files.get('xml')
    if xmlObject:
        fileObject = xmlObject.read()
        xml = etree.fromstring(fileObject)
        control_data = xml.xpath('//control_data')[0]
        config = {}

        logger.debug(config)

        for child in control_data:
            logger.debug(child)
            config[child.tag] = child.text

        logger.debug(config)

        guid = xml.xpath('//control_data/XML_GET_PARAM_guid/text()')[0]
        if (Print_System().save_xml(guid, fileObject)):
            result = Print_System().getFileMeta(guid, 'xml')

    return jsonify(results=result)


if __name__ == '__main__':
    try:
        port = int(config["Print_System"]["port"])
        host = config['File_Storage']["hostname"]
        app.run(host=host, port=port)
    except KeyboardInterrupt:
        pass

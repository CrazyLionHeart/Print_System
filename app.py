#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from .JsonApp import make_json_app
    import json

    import logging
    from logging.config import dictConfig

    from lxml import etree

    import requests

    from flask import jsonify, request, Response, make_response
    from flask import current_app, url_for
    from datetime import timedelta
    from .Print_System import Print_System
    from functools import update_wrapper

    from os import environ

    from .FileStorage.Storage import Storage

    from StringIO import StringIO
except ImportError, e:
    raise e

current_env = environ.get("APPLICATION_ENV", 'development')
basePath = environ.get("basePath", './')

with open('%s/config/%s/config.%s.json' %
          (basePath, current_env, current_env)) as f:
    config = json.load(f)
    dictConfig(config['loggingconfig'])

logger = logging.getLogger('print_system')

PS = Print_System(config)

JasperServer = config['JasperServer']

JasperUrl = 'http://%(hostname)s:%(port)s/jasperserver/flow.html' % JasperServer


def recursive_dict(element):
    return element.tag, \
        dict(map(recursive_dict, element)) or element.text


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

    def make_external_doc(guid, filename, database, callback=None):
        url = 'http://%s/ajax/submitajax.php' % '192.168.1.214'
        user = 'system'
        password = 'system_1234'

        auth = requests.auth.HTTPBasicAuth(user, password)
        payload = dict(file_name=guid,
                       file_hash=filename,
                       db_name=database,
                       ajtype='external_doc',
                       datatype='create')

        if callback is not None:
            payload['callback'] = callback

        logger.debug(payload)

        try:
            r = requests.post(url, auth=auth, params=payload)
            return r.json()
        except requests.exceptions.HTTPError as detail:
            raise Exception(
                "Не могу создать внешний документ: %s" %
                detail)
        except requests.exceptions.Timeout as detail:
            raise Exception("""Таймаут при отправке запроса на создание
                            внешнего документа: %s""" % detail)
        except requests.exceptions.ConnectionError as detail:
            raise Exception("Ошибка при подключении к ресурсу: %s" %
                            detail)
        except ValueError as detail:
            raise Exception("Сервис вместо ответа вернул bullshit")

    def get_pdf(config, guid, XML_URL):
        payload = dict(_flowId="viewReportFlow",
                       reportUnit=config['reportUnit'],
                       output=config['output'],
                       reportLocale="UTF-8",
                       j_username=JasperServer['username'],
                       j_password=JasperServer["password"],
                       XML_GET_PARAM_guid=guid,
                       XML_URL=XML_URL)

        user = JasperServer['username']
        password = JasperServer['password']
        auth = requests.auth.HTTPBasicAuth(user, password)

        logger.debug(payload)

        try:
            r = requests.get(url=JasperUrl, auth=auth, params=payload)
            return r.content
        except requests.exceptions.HTTPError as detail:
            raise Exception(
                "Не могу получить сгенерированную печатную форму: %s" %
                detail)
        except requests.exceptions.Timeout as detail:
            raise Exception("""Таймаут при отправке запроса в сервис генерации
                            печатной формы: %s""" % detail)
        except requests.exceptions.ConnectionError as detail:
            raise Exception("Ошибка при подключении к ресурсу: %s" %
                            detail)

    xmlObject = request.get_data(as_text=True)

    logger.debug(xmlObject)

    if xmlObject:
        fileObject = xmlObject

        parser = etree.XMLParser(recover=True, encoding='utf-8')
        xml = etree.parse(StringIO(fileObject), parser)

        count_elements = etree.XPath("count(//*[local-name() = $name])")

        if (count_elements(xml, name="print_data") != 1.0):
            raise Exception("No print_data")

        if (count_elements(xml, name="control_data") != 1.0):
            raise Exception("No control_data")
        else:
            control_data = xml.xpath('//control_data')[0]

        if (count_elements(xml, name="callback") == 1.0):
            callback = xml.xpath('//control_data/callback/text()')[0]
        else:
            callback = None

        XML_URL = config['XML_URL']

        for child in control_data:
            config[child.tag] = child.text

        guid = config['XML_GET_PARAM_guid']

        if (PS.save_xml(guid, fileObject)):
            pdf = get_pdf(config, guid, XML_URL)

            if (PS.save_pdf(guid, pdf)):
                if (config['print_type'] == 'print'):
                    result = PS.print_pdf(guid)
                    return jsonify(results=result)
                else:
                    database = "print_system"
                    content_type = 'application/pdf'
                    _, metadata = recursive_dict(control_data)

                    fs = Storage(db=database)

                    logger.debug("FS object: %s" % fs)

                    res = fs.put(pdf, content_type, json.dumps(metadata))

                    external_doc = make_external_doc(guid, res['filename'],
                                                     database, callback)

                    return jsonify(results=external_doc)
            else:
                raise Exception("""Не могу сохранить сгенерированную
                                печатную форму""")
        else:
            raise Exception("Не удалось сохранить XML")
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

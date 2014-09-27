#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    import json

    from lxml import etree

    import requests

    from raven.contrib.flask import Sentry
    from raven.middleware import Sentry as SentryMiddleware

    from flask import jsonify, request, Response
    from flask import url_for

    from FileStorage.Storage import Storage

    from config import config
    from JsonApp import make_json_app, crossdomain
    from Base_Print_System import Base_Print_System

    from Generators.filestorage import app as filestorage
    from Generators.print_serv import app as print_serv
    from Generators.rlab import app as rlab

except ImportError, e:
    raise e

PS = Base_Print_System(config)

JasperServer = config['JasperServer']

JasperUrl = 'http://%(hostname)s:%(port)s/jasperserver/flow.html' % JasperServer

dsn = "http://%s:%s@%s" % (config['Raven']['public'],
                           config['Raven']['private'],
                           config['Raven']['host'])

app = make_json_app(__name__)
app.config['SENTRY_DSN'] = dsn
sentry = Sentry(dsn=dsn, logging=True)
sentry.init_app(app)
app.wsgi = SentryMiddleware(app.wsgi_app, sentry.client)


def recursive_dict(element):
    return element.tag, \
        dict(map(recursive_dict, element)) or element.text


app = make_json_app(__name__)

url = 'http://%s/ajax/submitajax.php' % config["obs"]
user = 'system'
password = 'system_1234'

auth = requests.auth.HTTPBasicAuth(user, password)


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

        filtersMain = dict(groupOp="AND", rules=[dict(field="doc_pin",
                           data=guid, op="eq")]
                           )

        payload = dict(ajtype='jqGrid', datatype='docs_list',
                       filtersMain=json.dumps(filtersMain))

        try:
            r = requests.post(url, auth=auth, params=payload)
            app.logger.debug("Service response: %s" % r.text)
            headers = r.json()
            doc_name = headers[0]['name']
        except requests.exceptions.HTTPError as detail:
            raise Exception(
                u"Не могу получить свойства родительского документа: %s" %
                detail)
        except requests.exceptions.Timeout as detail:
            raise Exception(u"""Таймаут при отправке запроса на получение
                            свойств родительского документа: %s""" % detail)
        except requests.exceptions.ConnectionError as detail:
            raise Exception(u"Ошибка при подключении к ресурсу: %s" %
                            detail)
        except (ValueError, IndexError) as detail:
            raise Exception(
                u"Сервис вместо ответа вернул bullshit: :'%s'" % detail)

        payload = dict(file_name=doc_name,
                       file_hash=filename,
                       db_name=database,
                       ajtype='external_doc',
                       datatype='create',
                       doc_props=dict(
                           contragent_pin=headers[0]['contragent_pin'],
                       contragent_name=headers[0]['contragent_name'],
                       agent_pin=headers[0]['agent_pin'],
                       agent_name=headers[0]['agent_name']),
                       parent_doc_pin=guid)

        if callback is not None:
            payload['callback'] = callback

        app.logger.debug(payload)

        try:
            r = requests.post(url, auth=auth, params=payload)
            return r.json()
        except requests.exceptions.HTTPError as detail:
            raise Exception(
                u"Не могу создать внешний документ: %s" %
                detail)
        except requests.exceptions.Timeout as detail:
            raise Exception(u"""Таймаут при отправке запроса на создание
                            внешнего документа: %s""" % detail)
        except requests.exceptions.ConnectionError as detail:
            raise Exception(u"Ошибка при подключении к ресурсу: %s" %
                            detail)
        except ValueError as detail:
            raise Exception(
                u"Сервис вместо ответа вернул bullshit: %s" % detail)

    def get_pdf(serviceName, config, guid, **kwargs):

        app.logger.debug("serviceName: %s" % serviceName)
        app.logger.debug("config: %s" % config)
        app.logger.debug("guid: %s" % guid)
        app.logger.debug("XML_URL: %s" % config['XML_URL'])
        app.logger.debug("kwargs: %s" % kwargs)

        if serviceName == 'jasper':
            payload = dict(_flowId="viewReportFlow",
                           reportUnit=config['reportUnit'],
                           output=config['output'],
                           j_username=JasperServer['username'],
                           j_password=JasperServer["password"],
                           XML_GET_PARAM_guid=guid,
                           XML_URL=config['XML_URL'])

            user = JasperServer['username']
            password = JasperServer['password']
            auth = requests.auth.HTTPBasicAuth(user, password)

            app.logger.debug(payload)

            try:
                r = requests.get(url=JasperUrl, auth=auth, params=payload)
                return r.content
            except requests.exceptions.HTTPError as detail:
                raise Exception(u"""Не могу получить сгенерированную печатную
                                форму: %s""" % detail)
            except requests.exceptions.Timeout as detail:
                raise Exception(u"""Таймаут при отправке запроса в сервис
                                генерации печатной формы: %s""" % detail)
            except requests.exceptions.ConnectionError as detail:
                raise Exception(u"Ошибка при подключении к ресурсу: %s" %
                                detail)

        else:

            generator = globals()[serviceName]

            xml = PS.get_xml(guid)

            print_data = etree.tostring(
                xml.xpath('//print_data')[0], encoding='utf-8',
                pretty_print=True)

            app.logger.debug(kwargs)

            result = generator.app(print_data, **kwargs)

            if result:
                return result
            else:
                raise Exception("Service return no data")

    xmlObject = request.stream.read()

    if xmlObject:

        try:
            xml = etree.fromstring(xmlObject)
        except etree.XMLSyntaxError as e:
            raise Exception(e)

        kwargs = dict()

        count_elements = etree.XPath("count(//*[local-name() = $name])")

        if (count_elements(xml, name="print_data") != 1.0):
            raise Exception(u"No print_data")

        if (count_elements(xml, name="control_data") != 1.0):
            raise Exception(u"No control_data")
        else:
            control_data = xml.xpath('//control_data')[0]

        if (count_elements(xml, name="callback") == 1.0):
            callback = xml.xpath('//control_data/callback/text()')[0]
        else:
            callback = None

        if (count_elements(xml, name="serviceName") == 1.0):
            serviceName = xml.xpath("//serviceName/text()")[0]
        else:
            raise Exception(u"Unknown serviceName")

        if(count_elements(xml, name="storage_file_hash") == 1.0):
            kwargs['storage_file_hash'] = xml.xpath(
                "//control_data/storage_file_hash/text()")[0]

        if (count_elements(xml, name="storage_database") == 1.0):
            kwargs['storage_database'] = xml.xpath(
                "//control_data/storage_database/text()")[0]

        if (count_elements(xml, name='printFormName') == 1.0):
            kwargs['printFormName'] = xml.xpath(
                "//control_data/printFormName/text()")[0]

        for child in control_data:
            if child.tag != 'XML_URL':
                config[child.tag] = child.text

        guid = config['XML_GET_PARAM_guid']

        if (PS.save_xml(guid, xmlObject)):
            pdf = get_pdf(serviceName, config=config, guid=guid, **kwargs)

            if (PS.save_pdf(guid, pdf)):
                if (config['print_type'] == 'print'):
                    PS.print_pdf(guid)

                database = "print_system"
                content_type = 'application/pdf'
                _, metadata = recursive_dict(control_data)

                fs = Storage(db=database)

                app.logger.debug("FS object: %s" % fs)

                res = fs.put(pdf, content_type, json.dumps(metadata))

                if res:
                    external_doc = make_external_doc(guid, res['filename'],
                                                     database, callback)

                    return jsonify(results=external_doc)
                else:
                    return jsonify(results=False)
            else:
                raise Exception(u"""Не могу сохранить сгенерированную
                                печатную форму""")
        else:
            raise Exception(u"Не удалось сохранить XML")
    else:
        raise Exception(u"No data in xml param")


@app.route('/get_preview', methods=['GET'])
@crossdomain(origin='*')
def get_preview():
    guid = request.args.get("guid")
    if guid:
        pdf = PS.get_pdf(guid)
        return Response(pdf, direct_passthrough=True,
                        mimetype='application/pdf')
    else:
        raise Exception(u"No guid param")


@app.route('/get_jrxml', methods=['GET'])
@crossdomain(origin='*')
def get_jrxml():
    guid = request.args.get('guid')
    if guid is None:
        raise Exception(u"No guid in request")

    xml = PS.get_xml(guid)

    print_data = etree.tostring(
        xml.xpath('//print_data')[0], encoding='utf-8', pretty_print=True)

    return Response(print_data, direct_passthrough=True,
                    mimetype='text/xml', content_type='text/xml; charset=utf-8')


@app.route('/test', methods=['POST'])
@crossdomain(origin='*')
def test():

    xmlObject = request.files.get('xml')
    if xmlObject:
        fileObject = xmlObject.read()
        xml = etree.fromstring(fileObject)
        control_data = xml.xpath('//control_data')[0]
        config = {}

        for child in control_data:
            app.logger.debug(child)
            config[child.tag] = child.text

        app.logger.debug(config)

        guid = xml.xpath('//control_data/XML_GET_PARAM_guid/text()')[0]
        if (PS.save_xml(guid, fileObject)):
            result = PS.getFileMeta(guid, 'xml')

    return jsonify(results=result)

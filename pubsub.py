#!/usr/bin/env python
# -*- coding: utf-8 -*-

from twisted.internet import reactor, defer, threads
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet.task import deferLater
from twisted.web import static
from twisted.web.static import File
import twisted.web.error as error

from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.MIMEMultipart import MIMEMultipart
from email import Encoders


import cups

import urllib

import os
import time
from datetime import datetime
import calendar

from lxml import etree

import json

import types

import requests

import sys
sys.path.append("/usr/local/bin")

from urlparse import *

from AMQ import *

try:
    import logging
    from logging.config import dictConfig
    from loggingconfig import LOGGING, SENTRY_DSN
except Exception as e:
    raise e


try:
    from raven.handlers.logging import SentryHandler
except Exception as e:
    raise e

dictConfig(LOGGING)

logger = logging.getLogger()

amq = AMQ()

profile = "user"
tag = "print_system"

stringify = etree.XPath("string()")


def find(f, seq):
    """Return first item in sequence where f(item) == True."""
    for item in seq:
        if f(item):
            return item


def send_email(message_text, subject, sender, recipients, host, attach=None):
    """
    Send email to one or more addresses.
    """

    import mailer

    message = mailer.Message()
    message.From = sender
    message.To = recipients
    message.Subject = subject
    message.Body = message_text
    if not (attach is None):
        message.attach(attach)

    mailer = mailer.Mailer('localhost')

    d = deferLater(reactor, 0, mailer.send, message)
    d.addErrback(logger.error)
    return d


class Simple(Resource):
    isLeaf = True

    def errback(self, failure, request):
        # This will print the trace back in a way that looks like a python
        # exception.
        failure.printTraceback()
        # This will use the twisted logger. This is the best method, but
        logger.error(failure)
        # you need to import twisted log.

        # This will send a trace to the browser and close the request.
        request.processingFailed(failure)
        return None  # We have dealt with the failure. Clean it out now.

    def final(self, message, request, encoding):
        # Message will contain the message returned by callback1
        if not message is None:
            # This will write the message and return it to the browser.
            request.write(message.encode(encoding))

        request.finish()  # Done

    def __init__(self, uri):
        Resource.__init__(self)
        self.uri = uri

        self.conn = cups.Connection()

    def _put_to_monitor(self, data={}):
        """
           Отправляем задание на печать в очередь мониторинга. Сообщения из очереди прилетают с задержкой в 300 секунд
        """
        logger.debug("Send task to monitor")
        conf = {}
        conf['message_recipient'] = data['conf']['message_recipient']
        jobId = data["jobId"]
        conf['AMQ_SCHEDULED_DELAY'] = 60000
        conf['CamelCharsetName'] = 'UTF-8'

        message = jobId
        queue = "/queue/twisted_status"

        amq.producer(queue, message, conf)

    def _get_print_status(self, request):
        """
           Отправляем задание на печать.

        Доступные статусы:
    IPP_JOB_ABORTED = 8
    IPP_JOB_CANCELED = 7
    IPP_JOB_COMPLETED = 9
    IPP_JOB_HELD = 4
    IPP_JOB_PENDING = 3
    IPP_JOB_PROCESSING = 5
    IPP_JOB_STOPPED = 6
        """
        jobId = request.args.get('jobId', [None])[0]
        conf = request.getAllHeaders()
        Attributes = self.conn.getJobAttributes(int(jobId))
        # Определяем нужные статусы печати - которые мы не мониторим
        success = [7, 9]
        errors = [6, 8, 4]
        recipient = request.getHeader('message_recipient').split(",")

        # Если задание успешно напечаталось...
        if (Attributes['job-state'] in success):
            func_name = "toastr.success"
            func_args = ["Документ успешно напечатан!", "Печать завершена"]
            amq.Send_Notify(func_name, func_args, recipient, profile, tag)

        elif (Attributes['job-state'] in errors):
            func_name = "toastr.error"
            func_args = ["Во время печати документа произошла ошибка: %s" %
                         Attributes['job-state'], "Печать завершилась с ошибкой"]
            amq.Send_Notify(func_name, func_args, recipient, profile, tag)

        else:
            # Нет, задание еще висит в очереди на печать. Отправляем его в
            # очередь мониторинга
            self._put_to_monitor({"jobId": jobId, "conf": conf})
            func_name = "toastr.info"
            func_args = ["Печать еще не завершена.", "Идет печать"]
            amq.Send_Notify(func_name, func_args, recipient, profile, tag)

        request.write("Checked")
        request.finish()

    def parse_POST(self, request):
        """
              Получаем от пользователя XML
              Валидируем XML
              Отправляем XML на обработку в очередь
        """

        input_xml = request.args.get('xml', [None])[0]

        if input_xml is None:
                input_xml = request.content.read()
                if input_xml is None:
                    logger.error("No data")
                    return u'А где данные?'

        logger.debug("Input xml: %s" % input_xml)

        try:
            xml = etree.fromstring(input_xml)
        except (etree.XMLSyntaxError, ValueError) as detail:
            logger.error("Not valid XML %s" % detail)
            return u"Что за чушь вы мне подсунули? %s" % detail
        else:
            """
            Здесь задаем заголовки необходимые для обработки печатной формы
            """

            conf = {}

            # Установим заголовок для Camel
            conf["CamelCharsetName"] = "UTF-8"

            """
                   Разбиваем сообщение на две части - управляющую и данные
                   Управляющую часть ...
                   Часть с данным откладываем в ActiveMQ пока JasperReport
                   не придет за ней
             """

            control_data = xml.xpath('//control_data')
            logger.debug("print_data: %s" % control_data)

            for child in control_data[0]:
                if not (child.text is None):
                    if len(child.text):
                        conf[child.tag] = child.text

            print_data = xml.xpath('//print_data')
            logger.debug("print_data: %s" % print_data)

            if not (print_data is None):

                message = etree.tostring(
                    print_data[0], encoding='utf-8', pretty_print=True)

                queue = "/queue/jasper_print_data_%(XML_GET_PARAM_guid)s" % conf
                amq.producer(queue=queue,  message=message, conf=conf)

                message = etree.tostring(
                    control_data[0], encoding='utf-8', pretty_print=True)
                queue = "/queue/jasper_jasper_control"
                amq.producer(queue=queue, message=message, conf=conf)

                message = etree.tostring(
                    control_data[0], encoding='utf-8', pretty_print=True)
                queue = "/queue/jasper_control_data"
                amq.producer(queue=queue, message=message, conf=conf)

            else:
                logger.error("No print_data")
                return u"Нет блока данных print_data!"

        logger.debug('Ответ успешно  разобран')
        return u"Ответ успешно разобран"

    def _print_job(self, conf=None):
        # get printer name from filename
        printer_name = conf['printer']
        filename = conf['filename']
        path = conf['path']
        options = {}

        for num_copies in range(int(conf['count_copy'])):
            jobId = self.conn.printFile(printer_name, path, filename, options)

            d = deferLater(
                reactor, 0, self._put_to_monitor, {"jobId": jobId, "conf": conf})
            d.addErrback(logger.error)

    def render_GET(self, request):
        request.setHeader('Allow-Control-Allow-Origin', '*')
        if (self.uri == "print"):
            """
               Тут происходит обработка печатных форм
            """
            debug = False

            headers = request.getAllHeaders()
            args = request.args

            logger.debug("Print args: %s" % args)
            logger.debug("Print Headers: %s" % headers)

            guid = request.getHeader('xml_get_param_guid')
            FILE_NAME = "%(filename)s.%(type)s" % {
                'filename': guid, 'type': request.getHeader('output')}

            FILE_LOCATION = "/tmp/amq/%s" % FILE_NAME

            action = request.getHeader('print_type')

            if (action == "print"):
                """
                   Тут приходит уведомление от Camel о том что печатная форма  готова и
                   нужно ее отправить на печать
                """
                conf = request.getAllHeaders()
                conf['path'] = FILE_LOCATION
                conf['filename'] = guid

                statinfo = os.stat(FILE_LOCATION)
                if (statinfo.st_size > 1024):
                    self._print_job(conf)
                else:
                    recipient = conf['message_recipient'].split(",")

                    # Если задание успешно напечаталось...
                    func_name = "toastr.error"
                    func_args = [
                        "Ашипка генерации документа - неправильный шаблон или данные", "Печать отменена"]
                    amq.Send_Notify(
                        func_name, func_args, recipient, profile, tag)

                return "Send to print"

            elif (action == "preview"):
                """
                   Тут приходит уведомление от Camel о том что печатная форма  готова и
                   нужно уведомить получателя о этом
                """
                scheme, netloc, path, _, _ = urlsplit(
                    request.getHeader('XML_URL'))
                new_path = "/get_preview"
                query_string = "guid=%s" % FILE_NAME
                new_url = urlunsplit(
                    (scheme, netloc, new_path, query_string, _))
                content = '<a target="_blank" href="%s">Посмотреть документ</a>&#8230;' % new_url
                func_name = "toastr.success"
                func_args = [content, "Предпросмотр подготовлен"]
                recipient = request.getHeader('message_recipient').split(",")

                amq.Send_Notify(func_name, func_args, recipient, profile, tag)
                return "Send notify"

            elif (action == "email"):
                """
                   Тут приходит уведомление от Camel о том что печатная форма  готова и
                   нужно уведомить получателя об этом и отправить е-мейл
                """
                host = 'localhost'
                sender = request.getHeader("sender")
                recipients = request.getHeader("email_recipients")
                message = request.getHeader("message")
                subject = request.getHeader("subject")
                attach = FILE_LOCATION

                recipient = request.getHeader('message_recipient').split(",")

                df = send_email(
                    message, subject, sender, recipients, host, attach)
                df.addCallback(amq.Send_Notify, callbackArgs=(
                    "toastr.success", ["E-mail упешно отправлен!", "E-mail отправлен"], recipient, profile, tag))
                df.addErrback(amq.Send_Notify, errbackArgs=(
                    "toastr.error", ["При отправке e-mail возникли проблемы!", "E-mail не отправлен"], recipient, profile, tag))

                return "Задание поставлено"
            return "Test"

        elif (self.uri == "check_status"):
            """
               Тут мы обрабатываем проверку статуса печати документа
            """
            d = deferLater(reactor, 0, self._get_print_status, request)
            d.addErrback(logger.error)
            return NOT_DONE_YET

        elif (self.uri == "get_jrxml"):
            """
               Тут мы отдаем данные для JasperReport из которых он сгенерирует печатную форму
            """
            request.setHeader("Content-Type", "text/xml")
            logger.debug("get JRXML args: %s" % request.args)
            logger.debug("get JRXML Headers: %s" % request.getAllHeaders())
            guid = request.args.get('guid', [None])[0]
            logger.debug("Request: %s" % request.args)
            # Удаляем гланды через жопу - проверяем существует ли очередь с
            # данными
            url = "http://localhost:8161/admin/xml/queues.jsp"

            # Получаем текущий статус очередей в ActiveMQ
            res = requests.get(url, auth=('admin', 'Zona_baby009'))
            queues_status = xml = etree.fromstring(res.content)
            xpath = queues_status.xpath(
                "//queue[@name='jasper_print_data_%s']/stats" % guid)

            if not (xpath is None):
                for child in xpath:
                    if (child.attrib['size'] != 0):
                        queue = "/queue/jasper_print_data_%s" % guid
                        logger.debug(queue)
                        # print_data = amq.consumer(queue)
                        print_data = amq.consumer(queue)
                        logger.debug("Print_data: %s" % print_data)
                        return print_data
                    else:
                        logger.debug(child)
            else:
                logger.debug(xpath)

        elif (self.uri == "get_preview"):
            """
            Возращает пользователю печатную форму.
            Возвращаемый тип документа - application/pdf
            """
            logger.debug("get preview args: %s" % request.args)
            logger.debug("get preview Headers: %s" % request.getAllHeaders())

            guid = request.args.get("guid", [None])[0]

            FILE_LOCATION = "/tmp/amq/%s" % guid
            request.setHeader(
                'Content-Length',  str(os.path.getsize(FILE_LOCATION)))
            request.setHeader('Content-Disposition', 'inline')
            file = static.File(FILE_LOCATION)
            return file.render(request)

        elif (self.uri == "send_email"):
            return "E-mail NOT sended. Just demo"
        elif (self.uri == "printers"):
            printer = request.args.get('printer', [None])[0]
            request.setHeader("Content-Type", "application/json")
            if printer is None:
                return "%s" % json.dumps(self.conn.getPrinters(), sort_keys=True, indent=4)
            else:
                return "%s" % json.dumps(self.conn.getPrinterAttributes(printer), sort_keys=True, indent=4)
        else:
            return "OK"

    def render_POST(self, request):
        logger.debug(request)
        logger.debug(request.getAllHeaders())
        if (self.uri == "print"):
            content_type, encoding = 'text/html', 'UTF-8'
            request.setHeader('Content-Type', '%s; charset=%s' %
                              tuple(map(str, (content_type, encoding))))
            d = threads.deferToThread(self.parse_POST, request)
            d.addCallback(self.final, request, encoding)
            # We put this here in case the encoding raised an exception.
            d.addErrback(self.errback, request)
            # raise ValueError  # E5
            return NOT_DONE_YET

        elif (self.uri == "test"):
            logger.debug("Headers: %s" % request.getAllHeaders())
            logger.debug("Body: %s" % request.content.read())
            return "QE{"
        else:
            return "OK"


class Dispatcher(Resource):

    def getChild(self, name, request):
        return Simple(name)

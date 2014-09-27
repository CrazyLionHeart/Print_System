#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cups

try:
    import logging
    from lxml import etree
    from hashlib import md5
    import os
except ImportError as e:
    raise e

logger = logging.getLogger(__name__)


class Base_Print_System(object):

    def __init__(self, config=None):
        if config:
            self.config = config

    def save_xml(self, uuid, input_xml):
        try:
            xml = etree.fromstring(input_xml)

            data = etree.tostring(
                xml, encoding='utf-8', pretty_print=True)

            return Storage(uuid).put(data, filetype='xml')

        except (etree.XMLSyntaxError, ValueError) as detail:
            message = "Not valid XML: %s" % detail
            logger.error(message)
            raise Exception(message)

    def save_pdf(self, uuid, data):
        return Storage(uuid).put(data, filetype='pdf')

    def get_xml(self, uuid):
        xmlString = Storage(uuid).get(filetype='xml')

        return etree.fromstring(xmlString)

    def get_pdf(self, uuid):
        return Storage(uuid).get(filetype='pdf')

    def print_pdf(self, uuid):
        meta = self.getFileMeta(uuid, 'pdf')
        config = dict(self.config.items() + meta.items())
        return Print(config).print_file()

    def check_status(self, jobId):
        return Print(self.config).check_status(jobId)

    def printers(self, printer=None):
        return Print(self.config).printers(printer)

    def getFileMeta(self, uuid, filetype='xml'):
        return Storage(uuid).getMeta(filetype)


class Storage(object):

    def __init__(self, guid):
        logger.debug("Initializating Storage")
        self.guid = guid
        if guid:
            logger.debug("Setup path for object: {}".format(guid))
            self.digest = md5(guid).hexdigest()
            logger.debug("Digest: {}".format(self.digest))
            self.path = os.path.join(
                '/tmp', 'amq', self.digest[-1], self.digest[-2:])
            for i in ('xml', 'pdf'):
                try:
                    os.makedirs(os.path.join(self.path, i))
                except OSError:
                    pass
        else:
            logger.error("No guid")

    def put(self, data, filetype="xml"):
        with open(os.path.join(self.path, filetype, self.digest), 'w') as file:
            file.write(data)
            return True

    def get(self, filetype="xml"):
        with open(os.path.join(self.path, filetype, self.digest), 'r') as file:
            return file.read()

    def getMeta(self, filetype='xml'):
        meta = {}
        meta['fileSize'] = os.path.getsize(
            os.path.join(self.path, filetype, self.digest))
        meta['pathName'] = os.path.join(self.path, filetype)
        meta['filename'] = self.digest
        return meta


class Print(object):

    # Определяем нужные статусы печати - которые мы не мониторим
    success = [7, 9]
    errors = [6, 8, 4]

    def __init__(self, config=None):
        if config:
            logger.debug(config)
            required = ('printer', 'filename', 'pathName', 'count_copy')
            logger.debug(required)
            if all(k in config for k in required):
                self.config = config
            else:
                raise Exception("Missing required fields in config")
        else:
            raise Exception("Print class not configured")

        self.conn = cups.Connection()

    def check_status(self, jobId):
        """
        Доступные статусы:
            IPP_JOB_ABORTED = 8
            IPP_JOB_CANCELED = 7
            IPP_JOB_COMPLETED = 9
            IPP_JOB_HELD = 4
            IPP_JOB_PENDING = 3
            IPP_JOB_PROCESSING = 5
            IPP_JOB_STOPPED = 6
        """
        Attributes = self.conn.getJobAttributes(jobId)

        # Если задание успешно напечаталось...
        if (Attributes['job-state'] in self.success):
            return True

        elif (Attributes['job-state'] in self.errors):
            return False

        else:
            return None

    def print_file(self):
        printer_name = self.config['printer']
        filename = self.config['XML_GET_PARAM_guid']
        path = os.path.join(self.config['pathName'], self.config['filename'])

        options = {'sides': self.config['sides']}

        if self.config.get('lanscape'):
            options['landscape'] = True
        elif self.config.get('portrait'):
            options['portrait'] = True

        result = list()

        # Нужно формировать tuple из тасков
        for num_copies in range(int(self.config['count_copy'])):
            try:
                jobId = self.conn.printFile(printer_name, path, filename,
                                            options)
                result.append(jobId)
            except cups.IPPError as detail:
                raise Exception("Ошибка печати задания %s: %s" %
                                (self.config['XML_GET_PARAM_guid'],
                                 detail))

        return dict(jobId=result)

    def printers(self, printer=None):
        if printer:
            printer_stat = self.conn.getPrinterAttributes(printer)
        else:
            printer_stat = self.conn.getPrinters()
        return printer_stat

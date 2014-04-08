#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from stompy import Client as StompClient, Empty
except Exception as e:
    raise e

import json
from itertools import count

try:
    import logging
except Exception as e:
    raise e

logging.basicConfig(level=logging.DEBUG,
                    format=u'''%(filename)s[LINE:%(lineno)d]# %(levelname)-8s
                    [%(asctime)s]  %(message)s''')


class AMQ:

    def __init__(self):
        logging.debug("Создаем объект AMQ")

    def consumer(self, queue, num=1, callback=None):

        stomp = StompClient("localhost", 61613)
        stomp.connect()

        logging.debug("Начинаем забирать сообщение из очереди %s" % queue)

        headers = {
            # client-individual mode is necessary for concurrent processing
            # (requires ActiveMQ >= 5.2)
            'ack': 'client-individual',
            # the maximal number of messages the broker will let you work on at
            # the same time
            'activemq.prefetchSize': '1',
        }

        stomp.subscribe(queue, ack="client", conf=headers)

        try:
            for i in xrange(0, num) if num else count():
                if callback:
                    logging.debug("Забираем сообщение и передаем калбеку")
                    stomp.get(callback=callback)
                else:
                    frame = stomp.get()
                    logging.debug(frame.headers.get("message-id"))
                    logging.debug(frame.body)
                    stomp.ack(frame)
                    return frame.body
        except Empty as e:
            logging.error(e)
        finally:
            logging.debug(
                "Заканчиваем забирать сообщение и отписываемся от очереди")
            stomp.unsubscribe(queue)
            logging.debug("Закрываем подключение к очереди")
            stomp.disconnect()

    def producer(self, queue, message=None, conf={}):

        stomp = StompClient("localhost", 61613)
        stomp.connect()

        logging.debug("Кладем сообщение в %s: %s" % (queue, message))

        this_frame = stomp.put(
            item=message, destination=queue, persistent=True, conf=conf)
        logging.debug("Receipt: %s" % this_frame.headers.get("receipt-id"))
        stomp.disconnect()

    def Send_Notify(self, func_name="toastr.success", func_args=[], recipient=["*"], profile="user", tag="", callbackArgs=None, errbackArgs=None):
        if not (callbackArgs is None):
            func_name, func_args, recipient, profile = callbackArgs
        if not (errbackArgs is None):
            func_name, func_args, recipient, profile = errbackArgs
        message = {}
        message["body"] = {'func_name': func_name, 'func_args': func_args}
        message["recipient"] = recipient
        message["profile"] = profile
        message["tag"] = tag
        self.producer(queue="/topic/ControlMessage", message="%s" %
                      json.dumps(message))

import signal
import logging
import heapq
import threading
import time
import random
import urllib.request
import network
import xml.etree.ElementTree as ET
from http2 import HTTPMessage, HTTPRequest, HTTPResponse

logger = logging.getLogger()

class SSDPRemoteDevice:
    '''
    Represents a SSDP device in a remote subnet.
    '''

    def __init__(self, description_url):
        self.description_url = description_url
        self.description_data = None

        self.udn = None
        self.targets = ['upnp:rootdevice']

        self.get_data_from_server()

    def get_data_from_server(self):
        description_root = self.retrieve_device_description()

        self.extract_device_data(description_root)

    def retrieve_device_description(self):
        def remove_namespace(doc, namespace):
            ns = u'{{{}}}'.format(namespace)
            nsl = len(ns)
            for elem in doc.getiterator():
                if elem.tag.startswith(ns):
                    elem.tag = elem.tag[nsl:]

        http_response = urllib.request.urlopen(self.description_url)
        self.description_data = http_response.read()
        description_root = ET.fromstring(self.description_data)

        # without this we would have to specify the namespace on all
        # elements we want to search
        remove_namespace(description_root, 'urn:schemas-upnp-org:device-1-0')

        return description_root

    def extract_device_data(self, description_root):
        device = description_root.find('device')
        udn = device.find('UDN')
        device_type = device.find('deviceType')
        service_list = device.find('serviceList')

        self.udn = udn.text
        
        self.targets.append(device_type.text)

        for service_type in service_list.iter('serviceType'):
            self.targets.append(service_type.text)

    def __str__(self):
        return '<SSDPRemoteDevice url={}, udn={}>'.format(self.description_url, self.udn)

class SSDPMessage:
    '''
    Creates messages for a specific SSDP device.
    '''

    EXPIRY_FUDGE = 5
    SERVER_INFORMATION = 'Linux/2.6.15.2 UPnP/1.1 UPNPSPOOF/1.0'

    def __init__(self, device):
        self.ssdp_device = device

    def usn_for_target(self, target):
        usn = self.ssdp_device.udn

        if target != usn:
            usn = usn + '::' + target

        return usn

    def calculate_max_age(self, notification_interval):
        return notification_interval * 2 + SSDPMessage.EXPIRY_FUDGE

    def alive_request(self, target, notification_interval):
        max_age = self.calculate_max_age(notification_interval)

        headers = [
            ('HOST', network.multicast_host()),
            ('NTS', 'ssdp:alive'),
            ('NT', target),
            ('CACHE-CONTROL', HTTPMessage.max_age(max_age)),
            ('LOCATION', self.ssdp_device.description_url),
            ('SERVER', SSDPMessage.SERVER_INFORMATION),
            ('USN', self.usn_for_target(target))
        ]

        return HTTPRequest('NOTIFY', '*', headers)

    def byebye_request(self, target):
        headers = [
            ('HOST', network.multicast_host()),
            ('NTS', 'ssdp:byebye'),
            ('NT', target),
            ('USN', self.usn_for_target(target))
        ]

        return HTTPRequest('NOTIFY', '*', headers)

    def msearch_response(self, target, notification_interval):
        max_age = self.calculate_max_age(notification_interval)

        headers = [
            ('ST', target),
            ('CACHE-CONTROL', HTTPMessage.max_age(max_age)),
            ('DATE', HTTPMessage.current_date()),
            ('EXT', ''),
            ('LOCATION', self.ssdp_device.description_url),
            ('SERVER', SERVER_INFORMATION),
            ('USN', self.usn_for_target(target))
        ]

        return HTTPResponse(headers, code=200)

class SSDPSearchRequestHandler:
    '''
    Handles SSDP search requests targeted to a specific SSDP device.
    '''
    def __init__(self, device, notification_interval=1800):
        self.ssdp_device = device
        self.ssdp_message = SSDPMessage(device)
        self.notification_interval = notification_interval

    def handle(self, data, source_address):
        request = HTTPRequest.from_bytes(data)

        if request.method != 'M-SEARCH':
            logger.info('Ignoring %r request from %s', request.method, source_address)
            return

        search_target = request['st']

        if search_target in self.ssdp_device.targets:
            search_targets = [search_target]
        elif search_target == 'ssdp:all':
            search_targets = self.ssdp_device.targets
        else:
            logger.info('Ignoring M-SEARCH for %r from %s', st, source_address)
            sts = []

        for target in search_targets:
            # respond at a random time between 1 and MX seconds from now
            response = self.ssdp_message.msearch_response(target, self.notification_interval)
            
            send_msearch_reply(source_address, response)

    def send_msearch_reply(self, source_address, response):
        # TODO this should be posted to the outgoing network queue with delay=random.uniform(1, float(request['MX'])
        network.send_unicast_message(source_address, response)

        logger.info('Responded to M-SEARCH from %s: %r', network.pretty_sockaddr(source_address), response)

class SSDPAdvertiser(threading.Thread):
    '''
    Produces SSDP advertising events for a SSDP device at regular intervals.
    '''
    def __init__(self, device, notification_interval=1800):
        super(SSDPAdvertiser, self).__init__()

        self.ssdp_device = device
        self.ssdp_message = SSDPMessage(device)
        self.notification_interval = notification_interval

        self.stop_advertising = threading.Event()

    def run(self):
        while not self.stop_advertising.isSet():
            self.send_notify_alive_message()

            logger.info('Sending next SSDP alive notifications in %r seconds', self.notification_interval)

            self.stop_advertising.wait(self.notification_interval)

        self.send_notify_byebye_message()

    def join(self, timeout=None):
        logger.info('Stopping SSDP alive notifications')

        self.stop_advertising.set()

        super(SSDPAdvertiser, self).join(timeout)

    def send_notify_alive_message(self):
        logger.info('Sending SSDP alive notifications')

        for target in self.ssdp_device.targets:
            request = self.ssdp_message.alive_request(target, self.notification_interval)

            logger.info('Sending SSDP alive notification for %s', target)

            # TODO this should be posted to the outgoing network queue with delay=random.uniform(0, 0.1)
            network.send_multicast_message(request)

        logger.info('Sent SSDP alive notifications')

    def send_notify_byebye_message(self):
        logger.info('Sending SSDP byebye notifications')

        for target in self.ssdp_device.targets:
            request = self.ssdp_message.byebye_request(target)

            logger.info('Sending SSDP byebye notification for %s', target)
            # TODO this should be posted to the outgoing network queue with delay=random.uniform(0, 0.1)
            network.send_multicast_message(request)

        logger.info('Sent SSDP byebye notifications')

class SSDPDelayedResponseQueue(threading.Thread):
    '''
    Sends delayed SSDP messages in a linear fashion.
    '''

    def __init__(self):
        self.events = []
        self.execute_callbacks = True

    def run(self):
        while self.execute_callbacks:
            timeout = self.poll()
            logger.debug('Next scheduled SSDP response in %r', timeout)
            time.sleep(timeout)

    def halt(self):
        self.execute_callbacks = False

    def add(self, callback, args=None, delay=None):
        heapq.heappush(self.events, (time.time() + delay, callback, args))

    def poll(self):
        '''Execute any callbacks that are due, and return the time in seconds until the next event
        will be ready, or None if there are none pending.'''
        while True:
            if self.events:
                timeout = self.events[0][0] - time.time()
                if timeout >= 0:
                    # event not ready, so return the timeout
                    return timeout
                # event ready, execute it
                callback, args = heapq.heappop(self.events)[1:]
                callback(*([] if args is None else args))
            else:
                # no events pending, so there is no timeout
                return None

class SSDPTroll(threading.Thread):
    def __init__(self, ssdp_device):
        super(SSDPTroll, self).__init__()

        self.advertiser = SSDPAdvertiser(ssdp_device, 1800)
        self.search_handler = SSDPSearchRequestHandler(ssdp_device, 1800)
        self.mcast_server = network.MulticastServer(0x1000, self.search_handler)

        self.stop_troll = threading.Event()

    def run(self):
        def sigint(signalnum, handler):
            self.stop_troll.set()

        signal.signal(signal.SIGINT, sigint)

        self.mcast_server.start()
        self.advertiser.start()

        while not self.stop_troll.isSet():
            self.stop_troll.wait(1.0)

        self.advertiser.join()
        self.mcast_server.join()

import select
import socket
import logging
import random
import struct
import heapq
import time
import signal
import threading
import sys
import argparse
import itertools
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

formatter = logging.Formatter('%(asctime)s.%(msecs)03d;%(levelname)s;%(name)s;%(message)s',datefmt='%H:%M:%S')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# ------------------------------------------------------------------------------
# Networking
# ------------------------------------------------------------------------------
SSDP_MCAST_ADDR = '239.255.255.250'
SSDP_PORT = 1900

def multicast_host():
    return '{}:{:d}'.format(SSDP_MCAST_ADDR, SSDP_PORT)

def pretty_sockaddr(addr):
    '''Converts a standard Python sockaddr tuple and returns it in the normal text representation'''
    # IPv4 only?
    assert len(addr) == 2, addr
    return '{}:{:d}'.format(addr[0], addr[1])

def send_multicast_message(message):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, False)
    s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, b'\0'*4)
    #~ s.bind(('', 0)) # to the interface on any port
    s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 4)
    s.sendto(message.to_bytes(), (SSDP_MCAST_ADDR, SSDP_PORT))
    s.close() 

def send_unicast_message(self, address, message):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(address)
    sock.send(message.to_bytes())
    sock.close()

class DelayedEvents:
    '''A heap of delayed callbacks'''

    def __init__(self):
        self.events = []

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

# ------------------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------------------
class HTTPMessage:
    def __init__(self, first_line, headers, body):
        self.first_line = first_line
        self.headers = headers
        self.body = body

    def httpify_headers(self, headers):
        '''Build HTTP headers string, including the trailing CRLF's for each header'''

        def lines():
            for key, value in headers:
                assert key, key
                if value:
                    yield '{}: {}'.format(key, value)
                else:
                    yield key + ':'

        return '\r\n'.join(itertools.chain(lines(), ['']))

    def to_bytes(self):
        return(
            self.first_line + '\r\n' +
            self.httpify_headers(self.headers) + '\r\n'
        ).encode('utf-8') + self.body

    @classmethod
    def max_age(seconds):
        '''Returns the max-age value for the HTTP CACHE-CONTROL header'''
        return 'max-age={:d}'.format(seconds)

    @classmethod
    def current_date():
        '''Returns the current rfc1123 date for the HTTP Date header'''
        return time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime())

class HTTPRequest:
    __slots__ = 'method', 'path', 'protocol', 'headers', 'body', 'query'

    def __init__(self, method, resource, headers=None, body=b''):
        self.method = method
        
        split_result = urllib.parse.urlsplit(resource)
        self.query = urllib.parse.parse_qs(split_result.query)
        self.path = urllib.parse.unquote(split_result.path)
        if split_result.fragment:
            logger.warning('Unused fragment in HTTP request resource: %r', split_result.fragment)

        self.headers = headers or {}
        self.body = body

    def __setitem__(self, key, value):
        self.headers[key.upper()] = value.strip()

    def __getitem__(self, key):
        return self.headers[key.upper()]

    def __contains__(self, key):
        return key.upper() in self.headers

    def get(self, key):
        return self.headers.get(key.upper())

    def to_bytes(self):
        message = HTTPMessage(
            ' '.join((self.method, self.path, 'HTTP/1.1')),
            self.headers,
            self.body
        )

        return message.to_bytes()

    @classmethod
    def from_bytes(cls, buf):
        lines = (a.decode('utf-8') for a in buf.split(b'\r\n'))

        method, path, protocol = lines.__next__().split()
        
        request = cls(method, path)
        
        for h in lines:
            if h:
                name, value = h.split(':', 1)
                request[name] = value

        return request

class HTTPResponse:
    from http.client import responses

    def __init__(self, headers=None, body=b'', code=None, reason=None):
        self.headers = dict(headers) or {}
        self.body = body
        self.code = code
        self.reason = reason

    def to_bytes(self):
        message = HTTPMessage(
            'HTTP/1.1 {:03d} {}'.format(self.code, self.reason or self.responses[self.code]),
            self.headers.items(),
            self.body
        )

        return message.to_bytes()

# ------------------------------------------------------------------------------
# SSDP
# ------------------------------------------------------------------------------
class SSDPRemoteDevice:
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

class SSDPMessageFactory:
    EXPIRY_FUDGE = 5
    SERVER_INFORMATION = 'Linux/2.6.15.2 UPnP/1.1 UPNPSPOOF/1.0'

    def __init__(self, ssdp_device):
        self.ssdp_device = ssdp_device

    def usn_for_target(self, target):
        usn = self.ssdp_device.udn

        if target != usn:
            usn += '::' + target

        return usn

    def calculate_max_age(self, notification_interval):
        return notification_interval * 2 + EXPIRY_FUDGE

    def create_alive_request(self, target, notification_interval):
        max_age = self.calculate_max_age(notification_interval)

        headers = [
            ('HOST', multicast_host()),
            ('NTS', 'ssdp:alive'),
            ('NT', target),
            ('CACHE-CONTROL', HTTPMessage.max_age(max_age)),
            ('LOCATION', self.ssdp_device.description_url),
            ('SERVER', SERVER_INFORMATION),
            ('USN', self.usn_for_target(target))
        ]

        return HTTPRequest('NOTIFY', '*', headers)

    def create_byebye_request(self, target):
        headers = [
            ('HOST', multicast_host()),
            ('NTS', 'ssdp:byebye')
            ('NT', target),
            ('USN', self.usn_for_target(target))
        ]

        return HTTPRequest('NOTIFY', '*', headers)

    def create_msearch_response(self, target, notification_interval):
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

class SSDPAdvertiser:
    '''
    Sends SSDP notification events at regular intervals.
    '''
    logger = logger

    def __init__(self, ssdp_device, notification_interval=1800):
        self.events = DelayedEvents()
        self.send_alive_messages = True

        self.ssdp_device = ssdp_device
        self.ssdp_message_factory = SSDPMessageFactory(ssdp_device)
        self.notification_interval = notification_interval

    def run(self):
        self.send_notify_alive_message()
        self.send_notify_alive_messages()
        self.send_notify_byebye_message()

    def halt(self):
        self.stop_notify_alive_messages()

    def send_notify_alive_messages(self):
        while self.send_alive_messages:
            timeout = self.events.poll()
            logger.debug('Waiting for next advertisement event: %r', timeout)
            time.sleep(timeout)

    def stop_notify_alive_messages(self):
        self.send_alive_messages = False

    def send_notify_alive_message(self):
        self.logger.info('Sending SSDP alive notifications')

        for target in self.ssdp_device.targets:
            message = self.ssdp_message_factory.create_alive_request(target, self.notification_interval)

            self.logger.info('Sending SSDP alive notification for %s', target)
            self.schedule_notify_alive_multicast(request)

        self.logger.info('Sent SSDP alive notifications')

        self.schedule_next_notify_alive_message()

    def schedule_notify_alive_multicast(self, request):
        self.events.add(send_multicast_message, args=[request], delay=random.uniform(0, 0.1))

    def schedule_next_notify_alive_message(self):
        self.events.add(self.send_notify_alive_message, delay=self.notification_interval)
        self.logger.info('Next SSDP alive notification scheduled in %s seconds', self.notification_interval)

    def send_notify_byebye_message(self):
        self.logger.info('Sending SSDP byebye notifications')

        for target in self.ssdp_device.targets:
            message = self.ssdp_message_factory.create_byebye_request(target)

            self.logger.info('Sending SSDP byebye notification for %s', target)
            send_multicast_message(request)

        self.logger.info('Sent SSDP byebye notifications')

class SSDPResponder:
    '''
    Listens for, and responds to SSDP searches.
    '''
    logger = logger

    def __init__(self, ssdp_device, notification_interval=1800):
        self.events = DelayedEvents()
        self.listen_for_requests = True

        self.ssdp_device = proxy
        self.ssdp_message_factory = SSDPMessageFactory(ssdp_device)
        self.notification_interval = notification_interval

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.bind(('', SSDP_PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(SSDP_MCAST_ADDR) + struct.pack('I', socket.INADDR_ANY))

        while self.listen_for_requests:
            timeout = self.events.poll()
            readset = select.select([sock], [], [], timeout)[0]

            if sock in readset:
                # MTU should limit UDP packet sizes to well below this
                data, source_address = sock.recvfrom(0x1000)

                assert len(data) < 0x1000, len(source_address)
                
                self.process_message(data, source_address)

            else:
                self.logger.debug('Select timed out')

        sock.close()

    def halt(self):
        self.listen_for_requests = False

    def process_message(self, data, source_address):
        request = HTTPRequest.from_bytes(data)

        if request.method != 'M-SEARCH':
            self.logger.info('Ignoring %r request from %s', request.method, source_address)
            return

        st = request['st']

        if st in self.proxy.upnp_targets:
            sts = [st]
        elif st == 'ssdp:all':
            sts = self.proxy.upnp_targets
        else:
            self.logger.info('Ignoring M-SEARCH for %r from %s', st, source_address)
            sts = []

        for st in sts:
            # respond at a random time between 1 and MX seconds from now
            self.events.add(self.send_msearch_reply, args=[source_address, st], delay=random.uniform(1, float(request['MX'])))

    def send_msearch_reply(self, source_address, target):
        response = self.ssdp_message_factory.create_msearch_response(target, self.notification_interval)
        send_unicast_message(source_address, response)

        self.logger.info('Responded to M-SEARCH from %s: %r', pretty_sockaddr(source_address), response)

class SSDPSpoofer:
    def __init__(self, ssdp_device):
        self.advertiser = SSDPAdvertiser(ssdp_device, 1800)
        self.responder = SSDPResponder(ssdp_device, 1800)
        self.runnables = [self.ssdp_responder, self.ssdp_advertiser]

        self.stopped = threading.Event()

    def run(self):
        signal.signal(signal.SIGINT, self.halt)

        for runnable in self.runnables:
            thread = self.create_daemon_thread(runnable)
            thread.start()

        while not self.stopped.is_set():
            self.stopped.wait(1.0)

    def create_daemon_thread(self, runnable):
        def log_and_halt_on_exception(target):
            try:
                target()
            except Exception:
                logger.exception('Exception in thread %r:', threading.current_thread())
                raise
            finally:
                self.halt()

        thread = threading.Thread(
            name=runnable.__class__.__name__,
            target=log_and_halt_on_exception,
            args=[runnable.run]
        )

        thread.daemon = True

        return thread

    def halt(self, signalnum, handler):
        for runnable in self.runnables:
            runnable.halt()

        self.stopped.set()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server", help="Full HTTP url to the description.xml", default='http://x.x.x.x:8889/description.xml')
    args = parser.parse_args()

    remote_device = SSDPRemoteDevice(args.server)
    spoofer = SSDPSpoofer(remote_device)
    spoofer.run()

from .http import *
from .server import *
import select, socket, logging, random, struct

logger = logging.getLogger('ssdp')
logger.setLevel(logging.INFO)

EXPIRY_FUDGE = 5
SSDP_PORT = 1900
SSDP_MCAST_ADDR = '239.255.255.250'


import heapq, time

class Events:
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

class SSDPAdvertiser:
    '''
    Sends SSDP notification events at regular intervals.
    '''

    logger = logger

    def __init__(self, dms):
        self.dms = dms
        self.events = Events()

    @property
    def http_address(self):
        return self.dms.http_server.socket.getsockname()

    @property
    def usn_from_target(self):
        return self.dms.usn_from_target

    @property
    def notify_interval(self):
        return self.dms.notify_interval

    @property
    def notify_interfaces(self):
        yield socket.AF_INET, ('192.168.26.2', 0)

    def ssdp_multicast(self, family, addr, buf):
        s = socket.socket(family, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, False)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, b'\0'*4)
        #~ s.bind(('', 0)) # to the interface on any port
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 4)
        s.sendto(buf, (SSDP_MCAST_ADDR, SSDP_PORT))
        s.close() 

    def notify_byebye(self):
        for nt in self.dms.all_targets:
            for family, addr in self.notify_interfaces:
                buf = HTTPRequest('NOTIFY', '*', (
                    ('HOST', '{}:{:d}'.format(SSDP_MCAST_ADDR, SSDP_PORT)),
                    ('NT', nt),
                    ('USN', self.dms.usn_from_target(nt)),
                    ('NTS', 'ssdp:byebye'),)).to_bytes()
                self.ssdp_multicast(family, addr, buf)
        self.logger.debug('Sent SSDP byebye notifications')

    def notify_alive(self, last_interfaces=frozenset()):
        # TODO for each interface
        # sends should also be delayed 100ms by eventing
        interfaces = set(self.notify_interfaces)
        for if_ in interfaces - last_interfaces:
            self.logger.info('Notify interface came up: %s', if_)
        for if_ in last_interfaces - interfaces:
            self.logger.info('Notify interface went down: %s', if_)
        for family, addr in interfaces:
            for nt in self.dms.all_targets:
                buf = HTTPRequest('NOTIFY', '*', [
                    ('HOST', '{}:{:d}'.format(SSDP_MCAST_ADDR, SSDP_PORT)),
                    ('CACHE-CONTROL', 'max-age={:d}'.format(
                        self.dms.notify_interval * 2 + EXPIRY_FUDGE)),
                    ('LOCATION', 'http://{}:{:d}{}'.format(
                        addr[0],
                        self.http_address[1],
                        ROOT_DESC_PATH)),
                    ('NT', nt),
                    ('NTS', 'ssdp:alive'),
                    ('SERVER', SERVER_FIELD),
                    ('USN', self.usn_from_target(nt))]).to_bytes()
                self.events.add(
                    self.ssdp_multicast,
                    args=[family, addr, buf],
                    delay=random.uniform(0, 0.1))
            self.logger.debug('Sending SSDP alive notifications from %s', addr[0])
        self.events.add(self.notify_alive, delay=self.notify_interval, args=[interfaces])

    def run(self):
        self.events.add(self.notify_alive, delay=0.1)
        while True:
            timeout = self.events.poll()
            logger.debug('Waiting for next advertisement event: %r', timeout)
            time.sleep(timeout)


class SSDPResponder:
    '''
    Listens for, and responds to SSDP searches.
    '''

    logger = logger

    def process_message(self, data, peeraddr):
        request = HTTPRequest.from_bytes(data)
        if request.method != 'M-SEARCH':
            self.logger.debug('Ignoring %r request from %s', request.method, peeraddr)
            return
        st = request['st']
        if st in self.dms.all_targets:
            sts = [st]
        elif st == 'ssdp:all':
            sts = self.dms.all_targets
        else:
            self.logger.debug('Ignoring M-SEARCH for %r from %s', st, peeraddr)
            sts = []
        for st in sts:
            # respond at a random time between 1 and MX seconds from now
            self.events.add(
                self.send_msearch_reply,
                args=[peeraddr, st],
                delay=random.uniform(1, float(request['MX'])))

    @property
    def usn_from_target(self):
        return self.dms.usn_from_target

    @property
    def http_address(self):
        return self.dms.http_server.socket.getsockname()

    @property
    def max_age(self):
        return self.dms.notify_interval * 2 + EXPIRY_FUDGE

    def send_msearch_reply(self, peeraddr, st):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(peeraddr)
        buf = HTTPResponse([
                ('CACHE-CONTROL', 'max-age={:d}'.format(self.max_age)),
                ('DATE', rfc1123_date()),
                ('EXT', ''),
                ('LOCATION', 'http://{}:{:d}{}'.format(
                    sock.getsockname()[0],
                    self.http_address[1],
                    ROOT_DESC_PATH)),
                ('SERVER', SERVER_FIELD),
                ('ST', st),
                ('USN', self.usn_from_target(st))
            ], code=200).to_bytes()
        sock.send(buf)
        sock.close()
        self.logger.debug('Responded to M-SEARCH from %s: %r', pretty_sockaddr(peeraddr), buf)

    def __init__(self, dms):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        s.bind(('', SSDP_PORT))
        self.socket = s
        self.events = Events()
        self.dms = dms
        #~ self.update_multicast_membership()
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(SSDP_MCAST_ADDR) + struct.pack('I', socket.INADDR_ANY))

    #~ def update_multicast_membership(self):
        #~ from getifaddrs import getifaddrs
        #~ import struct, errno
        #~ try:
            #~ for ifaddr in getifaddrs():
                #~ if ifaddr.family == self.socket.family:
                    #~ self.logger.debug(
                        #~ 'Adding SSDPResponder socket to multicast group on interface %r',
                        #~ ifaddr.addr[0],)
                    #~ mreqn = struct.pack(
                        #~ '4s4si',
                        #~ socket.inet_aton(SSDP_MCAST_ADDR),
                        #~ socket.inet_aton(ifaddr.addr[0]),
                        #~ 0)
                    #~ try:
                        #~ self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreqn)
                    #~ except socket.error as exc:
                        #~ if exc.errno == errno.EADDRINUSE:
                            #~ self.logger.debug(exc)
                        #~ else:
                            #~ self.logger.exception(exc)
        #~ finally:
            #~ self.events.add(self.update_multicast_membership, delay=15)

    def run(self):
        while True:
            timeout = self.events.poll()
            readset = select.select([self.socket], [], [], timeout)[0]
            if self.socket in readset:
                # MTU should limit UDP packet sizes to well below this
                data, addr = self.socket.recvfrom(0x1000)
                assert len(data) < 0x1000, len(addr)
                self.process_message(data, addr)
            else:
                self.logger.debug('Select timed out')

import socket
import select
import struct
import threading
import logging

logger = logging.getLogger()

SSDP_MCAST_ADDR = '239.255.255.250'
SSDP_PORT = 1900

def pretty_sockaddr(addr):
    '''Converts a standard Python sockaddr tuple and returns it in the normal text representation'''
    # IPv4 only?
    assert len(addr) == 2, addr
    return '{}:{:d}'.format(addr[0], addr[1])

def multicast_host():
    return '{}:{:d}'.format(SSDP_MCAST_ADDR, SSDP_PORT)

class MulticastServer(threading.Thread):
    def __init__(self, buffer_size, handler):
        super(MulticastServer, self).__init__()

        self.stop_listening = threading.Event()
        self.buffer_size = buffer_size
        self.handler = handler
    
    #TODO use socketserver for this
    def run(self):
        logger.info('Listening for UDP multicast search requests')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.bind(('', SSDP_PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(SSDP_MCAST_ADDR) + struct.pack('I', socket.INADDR_ANY))

        while not self.stop_listening.isSet():
            readset = select.select([sock], [], [], 0.5)[0]

            if sock in readset:
                # MTU should limit UDP packet sizes to well below this
                data, source_address = sock.recvfrom(self.buffer_size)

                assert len(data) < bufsize, len(source_address)
                
                self.handler.handle(data, source_address)

        sock.close()

        logger.info('Stop listening for UDP multicast search requests')

    def join(self, timeout=None):
        self.stop_listening.set()
        super(MulticastServer, self).join(timeout)

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


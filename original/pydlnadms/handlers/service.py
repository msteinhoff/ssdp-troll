import collections
import socket
from ..soap import *
from ..services import ContentDirectoryService
from ..server import RESOURCE_PATH

def service(*args, **kwargs):
    return ServiceRequestHandler()(*args, **kwargs)

def recvall(sock, count):
    bufs = []
    while count > 0:
        b = sock.recv(count)
        if not b:
            break
        bufs.append(b)
        count -= len(b)
    return b''.join(bufs)
    

class ServiceRequestHandler:

    def __call__(self, context):
        soap_request = get_soap_request(context.request)
        self.dms = context.dms
        self.request = context.request
        soap_request_args = get_soap_request_args(
            recvall(context.socket, soap_request.content_length),
            soap_request.service_type,
            soap_request.action,)
        response_soap_args = getattr(self, 'soap_' + soap_request.action)(**soap_request_args)
        body = soap_action_response_body(
            soap_request.service_type,
            soap_request.action,
            response_soap_args.items())
        context.start_response(200, [
            ('Content-Length', str(len(body))),
            ('Content-Type', 'text/xml; charset="utf-8"'),
            ('Ext', '')])
        context.socket.sendall(body.encode('utf-8'))

    def soap_Browse(self, **soap_args):
        cds = ContentDirectoryService(
            self.dms.path,
            'http',
            self.request['host'],
            RESOURCE_PATH)
        return cds.Browse(**soap_args)

    def soap_GetSortCapabilities(self, **soap_args):
        return {'SortCaps': 'dc:title'}

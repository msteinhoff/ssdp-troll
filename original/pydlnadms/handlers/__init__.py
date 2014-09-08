from ..http import rfc1123_date, HTTPResponse
from .service import service
from .resource import *

def buffer(code, headers, body, context):
    context.start_response(code, headers)
    context.socket.sendall(body)

def xml_description(body, context):
    headers = [
        ('CONTENT-LENGTH', str(len(body))),
        ('CONTENT-TYPE', 'text/xml'),]
    return buffer(200, headers, body, context)

def error(code, context):
    headers = [('Content-Length', 0),]
    return buffer(code, headers, b'', context)

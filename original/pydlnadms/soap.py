from xml.etree import ElementTree as etree
import collections

from .http import *

def get_soap_request_args(raw_xml, service_type, action):
    # we're already looking at the envelope, perhaps I should wrap this
    # with a Document so that absolute lookup is done instead? TODO
    print(raw_xml)
    soap_request = etree.fromstring(raw_xml)
    action_elt = soap_request.find(
        '{{{s}}}Body/{{{u}}}{action}'.format(
            s='http://schemas.xmlsoap.org/soap/envelope/',
            u=service_type,
            action=action))
    in_args = {}
    for child_elt in action_elt.getchildren():
        assert not child_elt.getchildren()
        key = child_elt.tag
        value = child_elt.text
        assert key not in in_args, key
        in_args[key] = value
    return in_args

SOAPRequestHeader = collections.namedtuple(
    'SOAPRequestHeader',
    'service_type action content_length',
    verbose=False)

def get_soap_request(http_request):
    soapact = http_request['soapaction']
    assert soapact[0] == '"' and soapact[-1] == '"', soapact
    service_type, action = soapact[1:-1].rsplit('#', 1)
    content_length = int(http_request['content-length'])
    print(vars(), SOAPRequestHeader._fields)
    return SOAPRequestHeader(
        service_type=service_type,
        action=action,
        content_length=content_length)

def soap_action_response_body(service_type, action_name, arguments):
    # some clients expect the xml version to be at the very start of the document
    # maybe it's part of XML, maybe those clients suck. i don't know. don't move it.
    # addendum: apparently a leading backslash makes this work. don't move THAT.
    return '''\
<?xml version="1.0"?>
<s:Envelope
        xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <s:Body>
        <u:{actionName}Response xmlns:u="{serviceType}">
            {argumentXML}
        </u:{actionName}Response>
    </s:Body>
</s:Envelope>'''.format(
        actionName=action_name,
        argumentXML='\n'.join([
            '<{argumentName}>{value}</{argumentName}>'.format(
                argumentName=name, value=value) for name, value in arguments]),
        serviceType=service_type)

def didl_lite(content):
    return ('''<DIDL-Lite
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
    xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
    xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">
        ''' + content + r'</DIDL-Lite>')

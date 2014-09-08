from xml.etree import cElementTree as etree
from xml.sax.saxutils import escape as xml_escape
import collections
import itertools
import logging
import mimetypes
import os
import pprint
import sys
import logging as logger
import urllib.parse

from .dlna import *
from .soap import *
from .device import *


Service = collections.namedtuple(
    'Service',
    DEVICE_DESC_SERVICE_FIELDS + ('xmlDescription',))

def make_xml_service_description(actions, statevars):
    from xml.etree.cElementTree import Element, tostring, SubElement
    scpd = Element('scpd', xmlns='urn:schemas-upnp-org:service-1-0')
    specVersion = SubElement(scpd, 'specVersion')
    SubElement(specVersion, 'major').text = '1'
    SubElement(specVersion, 'minor').text = '0'
    actionList = SubElement(scpd, 'actionList')
    for action in actions:
        action_elt = SubElement(actionList, 'action')
        SubElement(action_elt, 'name').text = action[0]
        argumentList = SubElement(action_elt, 'argumentList')
        for name, dir, var in action[1]:
            argument = SubElement(argumentList, 'argument')
            SubElement(argument, 'name').text = name
            SubElement(argument, 'direction').text = dir
            SubElement(argument, 'relatedStateVariable').text = var
    serviceStateTable = SubElement(scpd, 'serviceStateTable')
    for name, datatype, *rest in statevars:
        stateVariable = SubElement(serviceStateTable, 'stateVariable', sendEvents='no')
        SubElement(stateVariable, 'name').text = name
        SubElement(stateVariable, 'dataType').text = datatype
        if rest:
            assert len(rest) == 1
            allowedValueList = SubElement(stateVariable, 'allowedValueList')
            for av in rest[0]:
                SubElement(allowedValueList, 'allowedValue').text = av
    return tostring(scpd)#.encode('utf-8')

SERVICE_LIST = []
for service, domain, version, actions, statevars in [
            ('ContentDirectory', None, 1, [
                ('Browse', [
                    ('ObjectID', 'in', 'A_ARG_TYPE_ObjectID'),
                    ('BrowseFlag', 'in', 'A_ARG_TYPE_BrowseFlag'),
                    ('StartingIndex', 'in', 'A_ARG_TYPE_Index'),
                    ('RequestedCount', 'in', 'A_ARG_TYPE_Count'),
                    ('Filter', 'in', 'A_ARG_TYPE_Filter'),
                    ('SortCriteria', 'in', 'A_ARG_TYPE_SortCriteria'),
                    ('Result', 'out', 'A_ARG_TYPE_Result'),
                    ('NumberReturned', 'out', 'A_ARG_TYPE_Count'),
                    ('TotalMatches', 'out', 'A_ARG_TYPE_Count')])], [
                ('A_ARG_TYPE_ObjectID', 'string'),
                ('A_ARG_TYPE_Result', 'string'),
                ('A_ARG_TYPE_BrowseFlag', 'string', [
                    'BrowseMetadata', 'BrowseDirectChildren']),
                ('A_ARG_TYPE_Index', 'ui4'),
                ('A_ARG_TYPE_Count', 'ui4'),
                ('A_ARG_TYPE_Filter', 'string'),
                ('A_ARG_TYPE_SortCriteria', 'string'),]),
            ('ConnectionManager', None, 1, (), ()),
            #('X_MS_MediaReceiverRegistrar', 'microsoft.com', 1, (), ()),
        ]:
    SERVICE_LIST.append(Service(
        serviceType='urn:{}:service:{}:{}'.format(
            'schemas-upnp-org' if domain is None else domain,
            service, version),
        serviceId='urn:{}:serviceId:{}'.format(
            'upnp-org' if domain is None else domain, service),
        SCPDURL='/'+service+'.xml',
        controlURL='/ctl/'+service,
        eventSubURL='/evt/'+service,
        xmlDescription=make_xml_service_description(actions, statevars)))

from .misc import guess_mimetype

import concurrent.futures
thread_pool = concurrent.futures.ThreadPoolExecutor(20)

from ffprobe import res_data

class ContentDirectoryService:

    Entry = collections.namedtuple('Entry', ['path', 'transcode', 'title', 'mimetype'])
    res_data = staticmethod(res_data)

    def __init__(self, root_id_path, res_scheme, res_netloc, res_path):
        self.root_id_path = root_id_path
        self.res_scheme = res_scheme
        self.res_netloc = res_netloc
        self.res_path = res_path

    def path_entries(self, path, name):
        entry_path = os.path.join(path, name)
        mimetype = guess_mimetype(entry_path)
        entry = self.Entry(path=entry_path, transcode=False, title=name, mimetype=mimetype)
        yield entry
        if mimetype and mimetype.split('/')[0] == 'video':
            # forward slashes cannot be used in normal file names >:D
            yield entry._replace(transcode=True, title=name+'/transcode')

    def list_dlna_dir(self, path):
        '''Yields entries to be shown for the given path with the metadata obtained while processing them.'''
        try:
            names = os.listdir(path)
        except Exception as exc:
            logger.warning('Error listing directory: %s', exc)
            return
        # this wants yield from itertools.chain.from_iterable... PEP 380
        for name in sorted(names, key=str.lower):
            for entry in self.path_entries(path, name):
                yield entry

    #<res size="1468606464" duration="1:57:48.400" bitrate="207770" sampleFrequency="48000" nrAudioChannels="6" resolution="656x352" protocolInfo="http-get:*:video/avi:DLNA.ORG_OP=01;DLNA.ORG_CI=0">http://192.168.24.8:8200/MediaItems/316.avi</res>

    def object_xml(self, parent_id, cdentry):
        '''Returns XML describing a UPNP object'''
        path = cdentry.path
        transcode = cdentry.transcode
        title = cdentry.title
        isdir = os.path.isdir(path)
        type, subtype = cdentry.mimetype.split('/')

        element = etree.Element(
            'container' if isdir else 'item',
            id=path, parentID=parent_id, restricted='1')
        # despite being optional, VLC requires childCount to browse subdirectories
        if isdir:
            element.set('childCount', str(sum(1 for _ in self.list_dlna_dir(path))))
        etree.SubElement(element, 'dc:title').text = title

        class_elt = etree.SubElement(element, 'upnp:class')
        if isdir:
            class_elt.text = 'object.container.storageFolder'
        else:
            class_elt.text = 'object.item.{type}Item'.format(**vars())
            # upnp:icon doesn't seem to work anyway, see the image/* res tag
            etree.SubElement(element, 'upnp:icon').text = urllib.parse.urlunsplit((
                self.res_scheme,
                self.res_netloc,
                self.res_path,
                urllib.parse.urlencode({'path': path, 'thumbnail': '1'}),
                None))

        # video res element
        content_features = DLNAContentFeatures()
        if transcode:
            content_features.support_time_seek = True
            content_features.transcoded = True
        else:
            content_features.support_range = True
        res_elt = etree.SubElement(element, 'res',
            protocolInfo='http-get:*:{}:{}'.format(
                '*' if isdir else 'video/mpeg' if transcode else cdentry.mimetype,
                content_features))
        res_elt.text = urllib.parse.urlunsplit((
            self.res_scheme,
            self.res_netloc,
            self.res_path,
            urllib.parse.urlencode([('path', path)] + ([('transcode', '1')] if transcode else [])),
            None))
        if not isdir and not transcode:
            try:
                res_elt.set('size', str(os.path.getsize(path)))
            except OSError as exc:
                logging.warning('%s', exc)
        if not isdir:
            for attr, value in self.res_data(path).items():
                res_elt.set(attr, str(value))

        # icon res element
        if type in {'video', 'image'}:
            # why the fuck does PNG_TN not work? what's so magical about JPEG_TN?
            # answer: it's because PNG isn't a supported profile for Panasonic Viera
            icon_res_element = etree.SubElement(
                element,
                'res',
                protocolInfo='http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN')
            icon_res_element.text = urllib.parse.urlunsplit((
                self.res_scheme,
                self.res_netloc,
                self.res_path,
                urllib.parse.urlencode({'path': path, 'thumbnail': '1'}),
                None))

        return etree.tostring(element, encoding='unicode')

    def path_to_object_id(root_path, path):
        # TODO prevent escaping root directory
        path = os.path.normpath(path)
        if path == root_path:
            return '0'
        else:
            return path

    def object_id_to_path(self, object_id):
        if object_id == '0':
            return self.root_id_path
        else:
            return object_id

    def Browse(self, BrowseFlag, StartingIndex, RequestedCount, ObjectID,
            Filter=None, SortCriteria=None):
        RequestedCount = int(RequestedCount)
        path = self.object_id_to_path(ObjectID)
        if BrowseFlag == 'BrowseDirectChildren':
            children = list(self.list_dlna_dir(path))
            start = int(StartingIndex)
            stop = (start + RequestedCount) if RequestedCount else None
            result_elements = list(thread_pool.map(
                self.object_xml,
                itertools.repeat(ObjectID),
                children[start:stop]))
            total_matches = len(children)
        else: # TODO check other flags
            parent_id = path_to_object_id(os.path.normpath(os.path.split(path)[0]))
            result_elements = [self.object_xml(parent_id, path, '??ROOT??', None)]
            total_matches = 1
        if logging.root.isEnabledFor(logging.DEBUG):
            logging.debug(
                'ContentDirectory::Browse result:\n%s',
                pprint.pformat(result_elements))
        return dict(
            Result=xml_escape(didl_lite(''.join(result_elements))),
            NumberReturned=len(result_elements),
            TotalMatches=total_matches)

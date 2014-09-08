import getpass, platform

ROOT_DEVICE_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaServer:1'
ROOT_DEVICE_MODEL_NAME = 'pydlnadms 2.0'
ROOT_DEVICE_FRIENDLY_NAME = \
    '{ROOT_DEVICE_MODEL_NAME}: {!r} on {!r}' \
    .format(getpass.getuser(), platform.node(), **vars())

ROOT_DEVICE_MANUFACTURER = 'Matt Joiner'
DEVICE_DESC_SERVICE_FIELDS = 'serviceType', 'serviceId', 'SCPDURL', 'controlURL', 'eventSubURL'

def make_device_desc(udn):
    from xml.etree.cElementTree import Element, tostring, SubElement
    root = Element('root', xmlns='urn:schemas-upnp-org:device-1-0')
    specVersion = SubElement(root, 'specVersion')
    SubElement(specVersion, 'major').text = '1'
    SubElement(specVersion, 'minor').text = '0'
    #SubElement(root, 'URLBase').text =
    device = SubElement(root, 'device')
    SubElement(device, 'deviceType').text = ROOT_DEVICE_DEVICE_TYPE
    SubElement(device, 'friendlyName').text = ROOT_DEVICE_FRIENDLY_NAME
    SubElement(device, 'manufacturer').text = ROOT_DEVICE_MANUFACTURER
    SubElement(device, 'modelName').text = ROOT_DEVICE_MODEL_NAME
    SubElement(device, 'UDN').text = udn
    iconList = SubElement(device, 'iconList')
    for icon_attrs in [
            ('image/png', 48, 48, 8, '/icon?path=VGC+Sonic.png'),
            ('image/png', 128, 128, 8, '/icon?path=VGC+Sonic+128.png'),]:
        icon = SubElement(iconList, 'icon')
        for name, text in zip(('mimetype', 'width', 'height', 'depth', 'url'), icon_attrs):
            SubElement(icon, name).text = str(text)
    serviceList = SubElement(device, 'serviceList')
    from .services import SERVICE_LIST
    for service in SERVICE_LIST:
        service_elt = SubElement(serviceList, 'service')
        for tag in DEVICE_DESC_SERVICE_FIELDS:
            SubElement(service_elt, tag).text = getattr(service, tag)
    return tostring(root, encoding='utf-8')#.encode('utf-8')

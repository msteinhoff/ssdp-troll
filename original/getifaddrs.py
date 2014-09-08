#!/usr/bin/env python3

from ctypes import (
    Structure, Union, POINTER,
    pointer, get_errno, cast,
    c_ushort, c_char, c_byte, c_void_p, c_char_p, c_uint, c_int, c_uint16, c_uint32
)
import collections
import ctypes.util
import ctypes
import os
import sys

IFF_LOOPBACK = 0x8
IFF_MULTICAST = 0x1000

sa_family_t = c_ushort

# TODO these C structs should mention the header they're defined in

class struct_sockaddr(Structure):
    _fields_ = [
        ('sa_family', c_ushort),
        ('sa_data', c_byte * 14),]

struct_in_addr = c_byte * 4

class struct_sockaddr_in(Structure):
    _fields_ = [
        ('sin_family', sa_family_t),
        ('sin_port', c_uint16),
        ('sin_addr', struct_in_addr)]

struct_in6_addr = c_byte * 16

class struct_sockaddr_in6(Structure):
    _fields_ = [
        ('sin6_family', c_ushort),
        ('sin6_port', c_uint16),
        ('sin6_flowinfo', c_uint32),
        ('sin6_addr', struct_in6_addr),
        ('sin6_scope_id', c_uint32)]

class union_ifa_ifu(Union):
    _fields_ = [
        ('ifu_broadaddr', POINTER(struct_sockaddr)),
        ('ifu_dstaddr', POINTER(struct_sockaddr)),]

class struct_ifaddrs(Structure):
    pass
struct_ifaddrs._fields_ = [
    ('ifa_next', POINTER(struct_ifaddrs)),
    ('ifa_name', c_char_p),
    ('ifa_flags', c_uint),
    ('ifa_addr', POINTER(struct_sockaddr)),
    ('ifa_netmask', POINTER(struct_sockaddr)),
    ('ifa_ifu', union_ifa_ifu),
    ('ifa_data', c_void_p),]

class py_ifaddrs:

    __slots__ = 'name', 'flags', 'family', 'addr', 'netmask'

    def __init__(self, **kwds):
        for key, value in kwds.items():
            setattr(self, key, value)

    def __repr__(self):
        s = self.__class__.__name__ + '('
        kwargs = {slot: getattr(self, slot) for slot in self.__slots__}
        kwargs['flags'] = hex(kwargs['flags'])
        s += ', '.join('{}={}'.format(k, v) for k, v in kwargs.items())
        return s + ')'

class struct_in_pktinfo(Structure):
    _fields_ = [
        ('ipi_ifindex', ctypes.c_uint),
        ('ipi_spec_dst', struct_in_addr),
        ('ipi_addr', struct_in_addr)]


libc = ctypes.CDLL(ctypes.util.find_library('c'))
if os.name == 'nt':
	_GetAdaptersAddresses = ctypes.windll.Iphlpapi
	
else:
	_getifaddrs = libc.getifaddrs
	_getifaddrs.restype = c_int
	_getifaddrs.argtypes = [POINTER(POINTER(struct_ifaddrs))]
	_freeifaddrs = libc.freeifaddrs
	_freeifaddrs.restype = None
	_freeifaddrs.argtypes = [POINTER(struct_ifaddrs)]

def ifap_iter(ifap):
    '''Iterate over linked list of ifaddrs'''
    ifa = ifap.contents
    while True:
        yield ifa
        if not ifa.ifa_next:
            break
        ifa = ifa.ifa_next.contents

def pythonize_sockaddr(sa):
    '''Convert ctypes Structure of sockaddr into the Python tuple used in the socket module'''
    from socket import AF_INET, AF_INET6, ntohs, ntohl, inet_ntop
    family = sa.sa_family
    if family == AF_INET:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in)).contents
        addr = (
            inet_ntop(family, sa.sin_addr),
            ntohs(sa.sin_port))
    elif family == AF_INET6:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in6)).contents
        addr = (
            inet_ntop(family, sa.sin6_addr),
            ntohs(sa.sin6_port),
            ntohl(sa.sin6_flowinfo),
            sa.sin6_scope_id)
    else:
        addr = None
    return family, addr

if os.name == 'nt':
	def getIPAddresses():
		from ctypes import Structure, windll, sizeof
		from ctypes import POINTER, byref
		from ctypes import c_ulong, c_uint, c_ubyte, c_char
		MAX_ADAPTER_DESCRIPTION_LENGTH = 128
		MAX_ADAPTER_NAME_LENGTH = 256
		MAX_ADAPTER_ADDRESS_LENGTH = 8
		class IP_ADDR_STRING(Structure):
			pass
		LP_IP_ADDR_STRING = POINTER(IP_ADDR_STRING)
		IP_ADDR_STRING._fields_ = [
			("next", LP_IP_ADDR_STRING),
			("ipAddress", c_char * 16),
			("ipMask", c_char * 16),
			("context", c_ulong)]
		class IP_ADAPTER_INFO (Structure):
			pass
		LP_IP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
		IP_ADAPTER_INFO._fields_ = [
			("next", LP_IP_ADAPTER_INFO),
			("comboIndex", c_ulong),
			("adapterName", c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
			("description", c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
			("addressLength", c_uint),
			("address", c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
			("index", c_ulong),
			("type", c_uint),
			("dhcpEnabled", c_uint),
			("currentIpAddress", LP_IP_ADDR_STRING),
			("ipAddressList", IP_ADDR_STRING),
			("gatewayList", IP_ADDR_STRING),
			("dhcpServer", IP_ADDR_STRING),
			("haveWins", c_uint),
			("primaryWinsServer", IP_ADDR_STRING),
			("secondaryWinsServer", IP_ADDR_STRING),
			("leaseObtained", c_ulong),
			("leaseExpires", c_ulong)]
		GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
		GetAdaptersInfo.restype = c_ulong
		GetAdaptersInfo.argtypes = [LP_IP_ADAPTER_INFO, POINTER(c_ulong)]
		adapterList = (IP_ADAPTER_INFO * 10)()
		buflen = c_ulong(sizeof(adapterList))
		rc = GetAdaptersInfo(byref(adapterList[0]), byref(buflen))
		if rc == 0:
			for a in adapterList:
				adNode = a.ipAddressList
				while True:
					ipAddr = adNode.ipAddress
					if ipAddr:
						yield ipAddr
					adNode = adNode.next
					if not adNode:
						break
	def getifaddrs():
		for s in getIPAddresses():
			yield py_ifaddr

else:
def getifaddrs():
    '''Wraps the C getifaddrs call, returns a list of pythonic ifaddrs'''
    ifap = POINTER(struct_ifaddrs)()
    result = _getifaddrs(pointer(ifap))
    if result == -1:
        raise OSError(get_errno())
    elif result == 0:
        pass
    else:
        assert False, result
    del result
    try:
        retval = []
        for ifa in ifap_iter(ifap):
            pia = py_ifaddrs(name=ifa.ifa_name, flags=ifa.ifa_flags)
            if ifa.ifa_addr:
                pia.family, pia.addr = pythonize_sockaddr(ifa.ifa_addr.contents)
            else:
                pia.family, pia.addr = None, None
            if ifa.ifa_netmask:
                pia.netmask = pythonize_sockaddr(ifa.ifa_netmask.contents)[1]
            else:
                pia.netmask = None
            retval.append(pia)
        return retval
    finally:
        _freeifaddrs(ifap)

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=0, stream=sys.stderr)
    import pprint
    pprint.pprint(getifaddrs())

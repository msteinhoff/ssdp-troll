import urllib.parse
import itertools

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
    def max_age(cls, seconds):
        '''Returns the max-age value for the HTTP CACHE-CONTROL header'''
        return 'max-age={:d}'.format(seconds)

    @classmethod
    def current_date(cls):
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

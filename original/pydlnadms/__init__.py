
from .device import *
from .ssdp import *
import threading



# TODO this could probably have named param to set the logger
def exception_logging_decorator(func):
    '''Log exceptions and reraise them.'''
    def callable():
        try:
            return func()
        except:
            logger.exception('Exception in thread %r:', threading.current_thread())
            raise
    return callable

class DigitalMediaServer:

    def __init__(self, port, path, notify_interval):
        # use a hash of the friendly name (should be unique enough)
        self.device_uuid = 'uuid:deadbeef-0000-0000-0000-{}'.format(
            '{:012x}'.format(abs(hash(ROOT_DEVICE_FRIENDLY_NAME)))[-12:])
        logger.info('DMS UUID is %r', self.device_uuid)
        self.notify_interval = notify_interval
        self.device_desc = make_device_desc(self.device_uuid)
        self.http_server = HTTPServer(port, self)
        self.ssdp_advertiser = SSDPAdvertiser(self)
        self.ssdp_responder = SSDPResponder(self)
        self.stopped = threading.Event()
        self.path = path
        self.run()

    def run_daemon(self, target):
        try:
            target()
        finally:
            self.stop()

    def stop(self):
        self.stopped.set()

    def run(self):
        for runnable in [self.http_server, self.ssdp_advertiser, self.ssdp_responder]:
            thread = threading.Thread(
                target=self.run_daemon,
                args=[exception_logging_decorator(runnable.run)],
                name=runnable.__class__.__name__)
            thread.daemon = True
            thread.start()
        self.stopped.wait()

    def on_server_accept(self, sock):
        threading.Thread(target=serve_http_client, args=(sock, self)).start()

    @property
    def all_targets(self):
        yield UPNP_ROOT_DEVICE
        yield self.device_uuid
        yield ROOT_DEVICE_DEVICE_TYPE
        for service in SERVICE_LIST:
            yield service.serviceType

    def usn_from_target(self, target):
        if target == self.device_uuid:
            return target
        else:
            return self.device_uuid + '::' + target

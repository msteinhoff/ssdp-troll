#!/usr/bin/env python3

def fix_etree_to_string():
    '''Fix xml.etree.ElementTree.tostring for python < 3.2'''
    import sys
    if sys.version_info.major >= 3 and sys.version_info.minor >= 2:
        return

    from xml.etree import ElementTree as etree
    _etree_tostring_original = etree.tostring
    def _etree_tostring_wrapper(*args, **kwargs):
        if kwargs.get('encoding') == 'unicode':
            del kwargs['encoding']
        return _etree_tostring_original(*args, **kwargs)
    etree.tostring = _etree_tostring_wrapper

def main():
    from argparse import ArgumentParser
    parser = ArgumentParser(
        usage='%(prog)s [options] [PATH]',
        description='Serves media from the given PATH over UPnP-AV and DLNA.')
    parser.add_argument(
        '-p', '--port', type=int, default=1337,
        help='media server listen PORT')
    parser.add_argument(
        '--logging_conf', '--logging-conf',
        help='Path of Python logging configuration file')
    parser.add_argument('--notify-interval', '-n', type=int, default=895,
        help='time in seconds between server advertisements on the network')
    parser.add_argument('path', nargs='?')
    namespace = parser.parse_args()

    import logging, logging.config
    if namespace.logging_conf is None:
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d;%(levelname)s;%(name)s;%(message)s',
            datefmt='%H:%M:%S')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    else:
        logging.config.fileConfig(namespace.logging_conf, disable_existing_loggers=False)
    logger = logging.getLogger('pydlnadms.main')

    path = namespace.path
    if path is None:
        import os
        path = os.curdir
    import os.path
    path = os.path.normpath(path)

    fix_etree_to_string()

    from pydlnadms import DigitalMediaServer
    DigitalMediaServer(namespace.port, path, notify_interval=namespace.notify_interval)

if __name__ == '__main__':
    main()

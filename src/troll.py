import logging
import argparse
import ssdp

def init_logging():
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d;%(levelname)s;%(name)s;%(message)s',datefmt='%H:%M:%S')

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("server", help="Full HTTP url to the description.xml", default='http://x.x.x.x:8889/description.xml')
    return parser.parse_args()

if __name__ == "__main__":
    init_logging()

    args = parse_arguments()

    remote_device = ssdp.SSDPRemoteDevice(args.server)
    troll = ssdp.SSDPTroll(remote_device)
    troll.run()

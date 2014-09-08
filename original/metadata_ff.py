#!/usr/bin/env python3

from ffprobe import res_data

def main():
    import argparse, logging, pprint, sys
    logging.basicConfig(level=logging.NOTSET)
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    namespace = parser.parse_args()
    pprint.pprint(res_data(namespace.file))

if __name__ == '__main__':
    main()

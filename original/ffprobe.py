#!/usr/bin/env python3

import errno
import logging
logger = logging.getLogger()
import os
import re
from subprocess import Popen, PIPE, CalledProcessError, list2cmdline

def parse_section(lines, section):
    for l in lines:
        if l.startswith('[/{section}]'.format(**vars())):
            return
        option, value = l.split('=', 1)
        yield option, value.rstrip()

def parse_stdout(lines):
    retval = {}
    for l in lines:
        section = re.match(r'\[(.+)\]', l).group(1)
        options = dict(parse_section(lines, section))
        index = options.get('index')
        if index is None:
            assert section not in retval, section
            retval[section] = options
        else:
            index = int(index)
            assert len(retval.setdefault(section, [])) == index, (section, index)
            retval[section].append(options)
    return retval

if os.name == 'nt':
    preexec_fn = None
else:
    from resource import setrlimit, RLIMIT_CPU
    def preexec_fn():
        # give the process 1 second, 2 if it treats SIGXCPU
        setrlimit(RLIMIT_CPU, (1, 2))

if os.name == 'nt':
    ffprobe_path = r'F:\ffmpeg-20120601-git-8a0efa9-win32-static\bin\ffprobe.exe'
else:
    ffprobe_path = 'ffprobe'
def ffprobe(path):
    args = [ffprobe_path, '-show_format', '-show_streams', path]
    process = Popen(
        args,
        stdout=PIPE,
        stderr=PIPE,
        preexec_fn=preexec_fn,)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise CalledProcessError(process.returncode, args)
    # TODO an alternative here could be to try several encodings in succession:
    # utf-8, cp1252, and the western european one whatever it is
    lines = (l.rstrip() for l in stdout.decode('cp1252', errors='ignore').splitlines())
    return parse_stdout(lines)

def res_data(path):
    try:
        data = ffprobe(path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            logger.error(exc)
            return {}
        else:
            raise
    except CalledProcessError as exc:
        logger.warning('{!r} failed with exit code {:d}'.format(
            exc.cmd,
            exc.returncode))
        return {}
    data = {k: v for k, v in data['FORMAT'].items() if v != 'N/A'}
    from datetime import timedelta
    attrs = {}
    if 'bit_rate' in data:
        attrs['bitrate'] = int(data['bit_rate'].rstrip('0').rstrip('.'))
    if 'duration' in data:
        attrs['duration'] = timedelta(seconds=float(data['duration']))
    return attrs

def main():
    logging.basicConfig(level=logging.NOTSET)
    import argparse, pprint, sys
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    namespace = parser.parse_args()
    pprint.pprint(ffprobe(namespace.file))

if __name__ == '__main__':
    main()

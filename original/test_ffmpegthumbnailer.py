import socket, subprocess

from socket import *
sock = socket(AF_INET, SOCK_STREAM)
sock.connect(('localhost', 3000))

process = subprocess.Popen([
        'ffmpegthumbnailer',
        '-i', 'dir/Boardwalk.Empire.S02E01.HDTV.XviD-ASAP.avi',
        '-o', '/dev/stdout',
        '-c', 'jpeg'],
    stdout=subprocess.PIPE)
sock.send(process.stdout.read())

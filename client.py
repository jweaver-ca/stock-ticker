# stockticker-server.py

import argparse
import sys
import socket
import selectors
import types
from enum import Enum
import random

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--server-ip",help="Server IP to connect to", default = '127.0.0.1')
parser.add_argument("-p", "--port",help="IP Port to listen on.", default = 11123)
args = parser.parse_args()

sel = selectors.DefaultSelector()
select_timeout = 10 # 10 while developing to make keyboard interrupts easier

def service_connection(key, mask):
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ:
        recv_data = sock.recv(1024)  # Should be ready to read
        if recv_data:
            print(f"Received {recv_data!r} from connection {data.connid}")
            data.recv_total += len(recv_data)
        if not recv_data or data.recv_total == data.msg_total:
            print(f"Closing connection {data.connid}")
            sel.unregister(sock)
            sock.close()
    if mask & selectors.EVENT_WRITE:
        if not data.outb and data.messages:
            data.outb = data.messages.pop(0)
        if data.outb:
            print(f"Sending {data.outb!r} to connection {data.connid}")
            sent = sock.send(data.outb)  # Should be ready to write
            data.outb = data.outb[sent:]

server_addr = (args.server_ip, args.port)
#for i in range(0, num_conns):
print(f"Starting connection to {server_addr}")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setblocking(False)
sock.connect_ex(server_addr)
events = selectors.EVENT_READ | selectors.EVENT_WRITE
sel.register(sock, events, data=None)

try:
    while True:
        events = sel.select(timeout=select_timeout)
        if events:
            for key, mask in events:
                service_connection(key, mask)
        # Check for a socket being monitored to continue.
        if not sel.get_map():
            break
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
finally:
    sel.close()


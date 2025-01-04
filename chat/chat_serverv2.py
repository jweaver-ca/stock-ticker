# from: https://stackoverflow.com/questions/7749341/basic-python-client-socket-example
# modified for python3

# v2 add selectors

# TODO: .bind localhost <-- need to change for actual network comms to work?
# TODO: handle mutliple rooms, for now just one room for all
# TODO: handle when buf > 1024 chars so its a single message
# TODO: handle removing clients when they disconnect
# TODO: handle a duplicate name trying to join
# TODO: ensure easy way to exit
# TODO: exit properly on error

import socket
#import threading
import selectors

sel = selectors.DefaultSelector()

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(('localhost', 8089))
serversocket.listen(5) # become a server socket, maximum 5 connections
#serversocket.settimeout(5) # .accept() blocks and ctrl-c doesn't break out of it.  this allows us to quit easier, but requires us to handle the except during accept

# NOTE: any use for supplying data here? Example in python selectors web page did...
sel.register(serversocket, selectors.EVENT_READ, "listen-new")

client_conns = dict()

# NOTE-v2: we dont need ClientThread class anymore?

running = True
while running:
    try:
        # if timeout expires, select() returns empty list
        # if we don't set timeout, select() blocks and on Windows, CTRL-C doesn't even break it
        events = sel.select(timeout=5.0)
        for key, mask in events:
            if key.data == "listen-new":
                # this is a new connection, get name and register with selector
                conn, addr = key.fileobj.accept()
                conn.setblocking(False)
                buf = conn.recv(64)
                name = buf.decode()
                client_conns[conn] = name
                print (f'[{name}] has joined. {len(client_conns)} total clients')
                sel.register(conn, selectors.EVENT_READ, None)
            else:
                # HMM: when would selectors.EVENT_WRITE ever be used??
                # this is an incoming message from a connected client, or ??
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    name = client_conns[conn]
                    print (f'READ event from {name}')
                    # TODO: doesn't handle big messages
                    buf = conn.recv(1024)
                    for iconn, iname in client_conns.items():
                        if name != iname:
                            print (f'Attempt to send to {iname}: {buf}')
                            iconn.send(buf)
    except KeyboardInterrupt:
        print ('keyboard interrupt')
        running = False

serversocket.close()



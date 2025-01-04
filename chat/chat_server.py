# from: https://stackoverflow.com/questions/7749341/basic-python-client-socket-example
# modified for python3

# TODO: .bind localhost <-- need to change for actual network comms to work?
# TODO: handle mutliple rooms, for now just one room for all
# TODO: handle when buf > 1024 chars so its a single message
# TODO: handle removing clients when they disconnect
# TODO: handle a duplicate name trying to join
# TODO: ensure easy way to exit
# TODO: exit properly on error

import socket
import threading

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(('localhost', 8089))
serversocket.listen(5) # become a server socket, maximum 5 connections
serversocket.settimeout(5) # .accept() blocks and ctrl-c doesn't break out of it.  this allows us to quit easier, but requires us to handle the except during accept

client_conns = []

class ClientThread(threading.Thread):
    def __init__(self, name, conn):
        super().__init__(name=name)
        self.conn = conn

    def run(self):
        # listen for messages from the client
        while True:
            buf = connection.recv(1024) # blocking
            if len(buf) > 0:
                msg = buf.decode('utf-8')
                print (f"from {self.name}: {msg}")
                for conn in client_conns:
                    if conn.name != self.name:
                        conn.send(bytes(f'{self.name}: {msg}'), 'utf-8')
            else:
                print ('huh?')

running = True
while running:
    conn_success = False
    try:
        connection, address = serversocket.accept()
        conn_success = True
    except KeyboardInterrupt:
        print ('keyboard interrupt')
        running = False
    except TimeoutError:
        print ('timeout error')
    if conn_success:
        buf = connection.recv(64)
        name = buf.decode()
        ct = ClientThread(name=name, conn=connection)
        client_conns.append(ct)
        ct.start()
        print (f'[{name}] has joined. {len(client_conns)} total clients')

serversocket.close()


# from: https://stackoverflow.com/questions/7749341/basic-python-client-socket-example
# modified for python3

# v2 add selectors
# V3:
# - add message ojbects
# - allow server to send shutdown requests to clients
# - handle client disconnect by server

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
import threading
#import pickle # for encoding messages to bytes -- whoops, use json instead
import json
import struct # for predictable integer (message size) encoding to bytes
import datetime

sel = selectors.DefaultSelector()

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(('localhost', 8089))
serversocket.listen(5) # become a server socket, maximum 5 connections
#serversocket.settimeout(5) # .accept() blocks and ctrl-c doesn't break out of it.  this allows us to quit easier, but requires us to handle the except during accept

lock = threading.Lock()

class ChatClient:
    def __init__(self, conn):
        self.conn = conn
        self.name = None

        self.initialized = False     # needs to receive name and get added to collection
        self.remaining_sz_bytes = 4
        self.sz_bytes = b''
        self.sz = 0                  # size of message in bytes
        self.msg = b''               # bytes of message being received
        self.message = None

    # received as first message from a connecting client
    def set_name(self, name):
        self.name = name

    # called when client sends data.  When a message is completed, process it
    # message starts with 4 byte int indicating size, then that # of bytes for
    # message body
    def add_bytes(self, b):
        try:
            while b: # always substract from byte array as its processed
                if self.remaining_sz_bytes > 0:
                    self.sz_bytes += b[0:self.remaining_sz_bytes]
                    b = b[self.remaining_sz_bytes:] # ans = no: could this throw error if only some of the sz_bytes came through on recv?
                    self.remaining_sz_bytes = 4 - len(self.sz_bytes)
                    if len(self.sz_bytes) == 4:
                        self.sz = struct.unpack('I', self.sz_bytes)[0]
                if b:
                    if len(b) + len(self.msg) < self.sz:
                        # not enough data in b to complete message
                        self.msg += b
                        b = b'' # stop loop
                    else:
                        # exactly enough or extra
                        required_bytes = self.sz - len(self.msg)
                        self.msg += b[0:required_bytes]
                        # TODO: process message
                        self.message = json.loads(self.msg.decode('utf-8'))
                        if self.message['TYPE'] == 'initconn':
                            # setname is the initial message
                            if self.name:
                                raise ValueError('Attempt to set name again for {self.name} -> {omsg["DATA"]}')
                            self.set_name(self.message['DATA'])
                        else:
                            process_message(self)
                        b = b[required_bytes:]
                        self.sz_bytes = b''
                        self.remaining_sz_bytes = 4
                        self.msg = b''
                        self.sz = 0
        except Exception as e:
            print (f"EXCEPTION: {repr(e)}")
            

# NOTE: any use for supplying data here? Example in python selectors web page did...
sel.register(serversocket, selectors.EVENT_READ, "listen-new")

client_conns = dict()   # key: socket, value: ChatClient object

# simple message object/dictionary
def msg(strType, strData):
    return {'TYPE': strType, 'DATA': strData}

# shortcut to get bytes (utf-8) of json-encoded message, including 4 byte size
# result from this function can go right into socket.send(...)
def bmsg(strType, strData):
    msgbytes = json.dumps(msg(strType, strData)).encode('utf-8')
    sz = len(msgbytes)
    return struct.pack('I', sz) + msgbytes

# process a message recieved from a client
#def process_message(msgobj, name):
def process_message(oClient):
    msgobj = oClient.message    
    name = oClient.name
    if msgobj['TYPE'] == 'msg':
        # incoming chat message
        chat_msg = msgobj['DATA']
        send_all(bmsg('chatmsg', f'[{datetime.datetime.now()}] {name}: {chat_msg}'))
    elif msgobj['TYPE'] == 'exit':
        print (f'exit message recieved from {name}')
        disconnect_client(oClient)
    
def disconnect_client(oClient):
    print (f'disconnect_client called for {oClient.name}')
    with lock: #Unsure how necessary or correct in logic this is...
        del client_conns[oClient.conn]
        sel.unregister(oClient.conn)
        oClient.conn.close()
    print (f'{oClient.name} has disconnected')
    send_all(bmsg('disconnect', oClient.name))

# msgobj: bytes of json message to send
def send_all(msgobj):
    #for iconn, iname in client_conns.items():
    #for iname, oClient in client_conns.items():
    for conn, oClient in client_conns.items():
        conn.send(msgobj)

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
                validconnection = True # true if client provides expected and valid initial message
                #conn.setblocking(False)
                try:
                    oClient = ChatClient(conn)
                    oClient.add_bytes(conn.recv(1024)) # should recieve name
                    print ('here')
                    if oClient.name:
                        if oClient.name in [x.name for x in client_conns.values()]:
                            conn.send(bmsg('error', f'client {name} already connected'))
                            print (f'Connection from [{addr}] refused, {name} already connected')
                            validconnection = False
                    else:
                        conn.send(bmsg('error', 'bad request'))
                        print(f'Bad request from [{addr}]: {msg}')
                        validconnection = False
                except Exception:
                    validconnection = False
                if validconnection:
                    conn.setblocking(False)
                    sel.register(conn, selectors.EVENT_READ, None)
                    conn.send(bmsg('conn-accept', None))
                    send_all(bmsg('joined', oClient.name))
                    client_conns[conn] = oClient
                    oClient.initialized = True
                    print (f'[{oClient.name}] has joined. {len(client_conns)} total clients')
                else:
                    conn.close()
            else:
                # HMM: when would selectors.EVENT_WRITE ever be used??
                # this is an incoming message from a connected client, or ??
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    oClient = client_conns[conn]
                    print (f'READ event from {oClient.name}')
                    try:
                        b = conn.recv(1024)
                    except Exception as e:
                        # ConnectionResetError?
                        print (f'conn.recv Exc: {e}')
                        b = None
                    if b:
                        oClient.add_bytes(b)
                    else:
                        # disconnected
                        disconnect_client(oClient)
                    # TODO: doesn't handle big messages
                    # MOVED to process_message
    except KeyboardInterrupt:
        print ('#keyboard interrupt')
        running = False
    except Exception as e:
        print (f'ERROR in main loop: {e}')
send_all(bmsg('server-exit', None))
serversocket.close()



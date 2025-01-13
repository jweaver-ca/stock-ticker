'''
    NOTES:
    A client can request a purchase of X shares at X price.  If the server recieves this request
    and the price of the stock in the purchase request no longer matches the actual price,
    what should happen?
        - refuse the purchase?
        - make the purchase if possible anyway?
            > if lower price, always. if higher price ...??
        - make this a client setting?
'''
# (useless comment from andrea)
#
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
import traceback
#import pickle # for encoding messages to bytes -- whoops, use json instead
import json
import struct # for predictable integer (message size) encoding to bytes
import datetime
import uuid
import types # SimpleNamespace for stock enum-ish construct?
from st_common import MessageReceiver

stock = types.SimpleNamespace(GOLD=1,SILVER=2,INDUSTRIAL=3,BONDS=4,OIL=5,GRAIN=6)
stock_names = [ 'GOLD', 'SILVER', 'INDUSTRIAL', 'BONDS', 'OIL', 'GRAIN' ]

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
                        process_message(self)
                        b = b[required_bytes:]
                        self.sz_bytes = b''
                        self.remaining_sz_bytes = 4
                        self.msg = b''
                        self.sz = 0
        except Exception as e:
            print (f"EXCEPTION: {repr(e)}")
            

class StockMarket:
    ''' StockMarket
        Data structure for maintaining stock prices
    '''
    INIT_VAL = 100      # stock price for each at game start
    OFF_MARKET_VAL = 0  # stock goes off market if <= this price
    SPLIT_VAL = 200     # stock will split if >= this price
    DIV_VAL = 105       # minimum stock price to pay dividends

    def __init__(self):
        self.market = {}
        for s in stock:
            self.market[s] = INIT_VAL

    def up(self, iStock, val):
        retval = {'split': False}
        if val < 0:
            raise ValueError(f'{iStock} up {val} invalid')
        self.market[iStock] += val
        if self.market[iStock] > SPLIT_VAL:
            retval['split'] = True
            self.market[iStock] = INIT_VAL
        return retval

    def down(self, iStock, val):
        retval = {'off-market': False}
        if val < 0:
            raise ValueError(f'{iStock} down {val} invalid')
        self.market[iStock] -= val
        if self.market[iStock] < OFF_MARKET_VAL:
            retval['off-market'] = True
            self.market[iStock] = INIT_VAL
        return retval

    def div(self, iStock, val):
        retval = {'div': False}
        if self.market[iStock] >= DIV_VAL:
            retval['div'] = True
        return retval
            
class Player:
    INIT_CASH = 5000

    def __init__(self, name, conn):
        self.name = name
        self.conn = conn
        self.message_receiver = MessageReceiver(f'msgrec-{name}', conn, process_message)
        self.message_receiver.data = name
        self.portfolio = [ 0 for i in range(len(stock_names)) ]
        self.id = uuid.uuid4()
        self.cash = Player.INIT_CASH

    # in case of reconnection
    def setClient(self, client):
        self.client = client
    
    # cash: amount of cash changed
    # less than zeros should be avoided by application, throw errors here
    def transaction(self, stock, shares, cash):
        self.portfolio[stock] += shares
        if self.portfolio[stock] < 0:
            raise ValueError('Less than zero shares')
        self.cash += cash
        if self.cash < 0:
            raise ValueError('Less than zero cash')
    

# NOTE: any use for supplying data here? Example in python selectors web page did...
sel.register(serversocket, selectors.EVENT_READ, "listen-new")

client_conns = dict()   # key: socket, value: ChatClient object
# TODO: players should replace client_conns, since connection is part of the Player class?
players = dict()  # key = player name

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
def process_message(message, playername):
    player = players[playername]
    if message['TYPE'] == 'msg':
        # incoming chat message
        chat_msg = message['DATA']
        send_all(bmsg('chatmsg', f'[{datetime.datetime.now()}] {name}: {chat_msg}'))
    elif message['TYPE'] == 'exit':
        print (f'exit message recieved from {name}')
        disconnect_client(player)
    
def disconnect_client(player):
    print (f'disconnect_client called for {player.name}')
    with lock: #Unsure how necessary or correct in logic this is...
        #del client_conns[oClient.conn]
        del players[player.name]
        sel.unregister(player.conn)
        player.conn.close()
    print (f'{player.name} has disconnected')
    send_all(bmsg('disconnect', player.name))

# msgobj: bytes of json message to send
def send_all(msgobj):
    #for iconn, iname in client_conns.items():
    #for iname, oClient in client_conns.items():
    for player in players.values():
        player.conn.send(msgobj)

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
                    msgrec = MessageReceiver('client', conn)
                    msgrec.add_bytes(conn.recv(1024))
                    init_msg = msgrec.get_message()  # blocks
                    print ("initial msg received from connecting client")
                    name = init_msg['DATA']
                    if name:
                        if name in [x.name for x in players.values()]:
                            conn.send(bmsg('error', f'client {name} already connected'))
                            print (f'Connection from [{addr}] refused, {name} already connected')
                            validconnection = False
                except Exception:
                    print(traceback.format_exc())
                    validconnection = False
                if validconnection:
                    conn.setblocking(False)
                    players[name] = Player(name, conn)
                    sel.register(conn, selectors.EVENT_READ, players[name])
                    conn.send(bmsg('conn-accept', None))
                    send_all(bmsg('joined', name))
                    #client_conns[conn] = oClient
                    print (f'[{name}] has joined. {len(client_conns)} total clients')
                else:
                    conn.close()
            else:
                # HMM: when would selectors.EVENT_WRITE ever be used??
                # this is an incoming message from a connected client, or ??
                player = key.data
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    msgrec = player.message_receiver

                    print (f'READ event from {player.name}')
                    try:
                        b = conn.recv(1024)
                    except Exception as e:
                        # ConnectionResetError?
                        print (f'conn.recv Exc: {e}')
                        b = None
                    if b:
                        msgrec.add_bytes(b)
                    else:
                        # disconnected
                        disconnect_client(player)
                    # TODO: doesn't handle big messages
                    # MOVED to process_message
    except KeyboardInterrupt:
        print ('#keyboard interrupt')
        running = False
    except Exception as e:
        print (f'ERROR in main loop: {e}')
        print (traceback.format_exc())
send_all(bmsg('server-exit', None))
serversocket.close()



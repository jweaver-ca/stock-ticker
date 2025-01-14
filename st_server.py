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
import random # for die rolls
#import pickle # for encoding messages to bytes -- whoops, use json instead
import json
import struct # for predictable integer (message size) encoding to bytes
import datetime
import time
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

class Player:
    INIT_CASH = 5000

    def __init__(self, name, conn):
        self.name = name
        self.conn = conn
        self.message_receiver = MessageReceiver(f'msgrec-{name}', conn, process_message)
        self.message_receiver.data = name
        self.portfolio = list( 0 for i in range(len(stock_names)) )
        # NOPE self.pending_order = [ 0 for i in range(len(stock_names)) ]
        self.id = uuid.uuid4()
        self.cash = Player.INIT_CASH
        self.game = None # reference to StockTickerGame
        self.ready_start = False

    # cash: amount of cash changed
    # less than zeros should be avoided by application, throw errors here
    def transaction(self, stock, shares, cash):
        self.portfolio[stock] += shares
        if self.portfolio[stock] < 0:
            raise ValueError('Less than zero shares')
        self.cash += cash
        if self.cash < 0:
            raise ValueError('Less than zero cash')
    
    def summary(self):
        '''
        Summary of this player's cash, net worth and market portfolio
        for sending to client
        '''
        portfolio_val = 0
        for i, shares in enumerate(self.portfolio):
            price = self.game.market[i]
            portfolio_val += shares * price
        networth = self.cash + int(portfolio_val/100)
        return {
            'cash': self.cash,
            'networth': networth,
            'portfolio': self.portfolio
        }

class DiceRollTimer(threading.Thread):
    def __init__(self, interval, fn_action):
        super().__init__()
        self.interval = interval
        self.action = fn_action
        self.daemon = True
        self.paused = False
        self.restart_event = threading.Event()

    def run(self):
        while True:
            print (f"Timer countdown started! {self.interval} seconds")
            send_all(bmsg('actiontime', self.interval))
            time.sleep(self.interval)
            if self.paused:
                self.restart_event.clear()
                self.restart_event.wait()
                # NOTE: if paused, assume when unpaused that all players want die roll immediately
                self.paused = False
            self.action()

    def pause(self):
        self.paused = True

    def restart(self):
        if self.paused:
            self.paused = False
        if not self.restart_event.is_set():
            self.restart_event.set()

class StockTickerGame():
    '''
    Encapsulates an entire session of Stock Ticker including the market
    players.
    '''
    def __init__(self):
        self.INIT_VAL = 100      # stock price for each at game start
        self.OFF_MARKET_VAL = 0  # stock goes off market if <= this price
        self.SPLIT_VAL = 200     # stock will split if >= this price
        self.DIV_VAL = 105       # minimum stock price to pay dividends

        self.STOCK_DIE = tuple(range(len(stock_names))) # should produce 0-5
        self.ACTION_DIE = ('UP', 'DOWN', 'DIV')
        self.AMOUNT_DIE = (5, 10, 20)

        self.option_ignore_nopay_divrolls = True
        self.option_timer_seconds = 1

        #self.stock_names = stock_names hmm not needed
        self.market = [ self.INIT_VAL for i in range(len(stock_names)) ]
        self.players = dict()
        self.started = False # flag indicating if game underway or not

        #self.roll_timer = threading.Timer(self.option_timer_seconds, self.market_action)
        self.roll_timer = DiceRollTimer(self.option_timer_seconds, self.market_action)
        self.market_lock = threading.Lock()
        # REMOVE # self.buysell_call_id = None # id of the last buysell_call sent out to players

    def add_player(self, player):
        if player.name in (p.name for p in self.players.values()):
            raise ValueError(f"Player [{player.name}] already in game")
        if player.game is not None:
            raise ValueError(f"Player [{player.name}] is in another game")
        self.players[player.name] = player
        player.game = self

    def remove_player(self, playername):
        del self.players[playername]

    def market_summary(self):
        '''
        Get market summary to send to clients/players
        [(stockval, bln_pays_dividend), ... for each stock
        '''
        return [(val, val>self.DIV_VAL) for val in self.market]

    def all_players_ready(self):
        return all([p.ready_start for p in self.players.values()])

    def start_game(self):
        self.started = True
        self.roll_timer.start()

    def die_roll(self):
        retval = {
            'stock': random.choice(self.STOCK_DIE),
            'action': random.choice(self.ACTION_DIE),
            'amount': random.choice(self.AMOUNT_DIE),
            'div_nopay': False # only true if action is div but stock too low to pay
        }
        # result will say if dividend will be paid so that caller can decide to ignore it if not
        if retval['action'] == 'DIV':
            retval['div_nopay'] = not self.pays_dividend(retval['stock'])
        return retval

    def process_order(self, player, buysell_order):
        ''' Apply the buy/sell order '''
        total_cents_spent = 0
        approve_data = {
            'reqid': buysell_order['reqid'],
            'prices': [],
            'reject-reason': None
        }
        with self.market_lock:
            new_shares_totals = player.portfolio.copy()
            for i, (shares, expected_price) in enumerate(buysell_order['data']):
                approve_data['prices'].append(self.market[i])
                total_cents_spent += shares * self.market[i]
                new_shares_totals[i] += shares
            total_dollars_spent = int(total_cents_spent / 100)
            print (f'{total_dollars_spent=} {new_shares_totals=}')
            bln_enough_cash = total_dollars_spent <= player.cash
            bln_enough_shares = all((s>=0 for s in new_shares_totals)) 
            if bln_enough_cash and bln_enough_shares:
                player.cash -= total_dollars_spent
                player.portfolio = new_shares_totals
                approve_data['cost'] = total_dollars_spent
                bln_approved = True
            else:
                approve_data['cost'] = 0
                reasons = []
                if not bln_enough_cash:
                    reasons.append('not enough cash')
                if not bln_enough_shares:
                    reasons.append('not enough shares')
                if reasons:
                    approve_data['reject-reason'] = '/'.join(reasons)
                else:
                    approve_data['reject-reason'] = '???'
                bln_approved = False
            approve_data['approved'] = bln_approved
            approve_data['cash'] = player.cash
            approve_data['portfolio'] = player.portfolio
        player.conn.send(bmsg('approve', approve_data))
        
    # NOTE: this should be called with the market_lock acquired
    # TODO: can/should we move the message sending outside the locked area?
    def _split(self, i_stock):
        for player in self.players.values():
            # dividend 20 paid out
            div_dollars = int(player.portfolio[i_stock] * 0.2)
            player.cash += div_dollars
            shares_gained = player.portfolio[i_stock]
            player.portfolio[i_stock] += shares_gained
            split_msg_data = {
                'stock': i_stock,
                'newprice': self.INIT_VAL,
                'div': self.INIT_VAL >= self.DIV_VAL, 
                'shares': player.portfolio[i_stock],
                'gained': shares_gained,
                'divpaid': div_dollars
            }
            player.conn.send(bmsg('split', split_msg_data))
        self.market[i_stock] = self.INIT_VAL
        
    def _bust(self, i_stock):
        for player in self.players.values():
            shares_lost = player.portfolio[i_stock]
            player.portfolio[i_stock] = 0
            bust_msg_data = {
                'stock': i_stock,
                'newprice': self.INIT_VAL,
                'shares': 0,
                'lost': shares_lost
            }
            player.conn.send(bmsg('offmarket', bust_msg_data))
        self.market[i_stock] = self.INIT_VAL

    def market_action(self):
        '''Rolls dice and applies changes to the game'''
        # roll the dice
        roll = self.die_roll()
        attempts = 1
        max_attempts = 100
        if self.option_ignore_nopay_divrolls:
            while roll['div_nopay'] and attempts < max_attempts:
                if attempts == max_attempts:
                    raise RuntimeError(f"Too many no-pay dividend die rolls")
                attempts += 1
                roll = self.die_roll()
        print (f'{roll=}')
        
        send_all(bmsg('roll', roll))
        price_change_data = None
        with self.market_lock:
            if roll['action'] == 'UP':
                self.market[roll['stock']] += roll['amount']
                if self.market[roll['stock']] >= self.SPLIT_VAL:
                    self._split(roll['stock'])
                price_change_data = {'stock': roll['stock'],
                        'amount': roll['amount'],
                        'newprice': self.market[roll['stock']],
                        'div': self.pays_dividend(roll['stock'])
                    }
            if roll['action'] == 'DOWN':
                self.market[roll['stock']] -= roll['amount']
                if self.market[roll['stock']] <= self.OFF_MARKET_VAL:
                    self._bust(roll['stock'])
                price_change_data = {'stock': roll['stock'],
                        'amount': -roll['amount'],
                        'newprice': self.market[roll['stock']],
                        'div': self.pays_dividend(roll['stock'])
                    }
            if roll['action'] == 'DIV' and self.pays_dividend(roll['stock']):
                for player in self.players.values():
                    # dividend 20 paid out
                    div_dollars = int(player.portfolio[roll['stock']] * roll['amount']/100)
                    if div_dollars:
                        player.cash += div_dollars
                        div_msg_data = {
                            'stock': roll['stock'],
                            'amount': roll['amount'],
                            'divpaid': div_dollars,
                            'playercash': player.cash
                        }
                        player.conn.send(bmsg('div', div_msg_data))
        if price_change_data:
            send_all(bmsg('market', price_change_data))
                

    def pays_dividend(self, i_stock):
        return self.market[i_stock] >= self.DIV_VAL

    def status(self):
        # NOTE: may add more details (e.g. paused,etc?), so using dictionary even though just 1 item...
        return {'started': self.started}

# NOTE: any use for supplying data here? Example in python selectors web page did...
sel.register(serversocket, selectors.EVENT_READ, "listen-new")

# NOTE: One day server will be able to host multiple games so conceptually keeping
#       the design such that the change will be easier
game = StockTickerGame()
players = dict()  # key = player name. *all* players in system

# simple message object/dictionary
def msg(str_type, data):
    '''
    data: can be a string, number, list, tuple, dictionary, boolean, None
        see json.dumps() conversion table
    '''
    return {'TYPE': str_type, 'DATA': data}

# shortcut to get bytes (utf-8) of json-encoded message, including 4 byte size
# result from this function can go right into socket.send(...)
def bmsg(str_type, data):
    msgbytes = json.dumps(msg(str_type, data)).encode('utf-8')
    sz = len(msgbytes)
    return struct.pack('I', sz) + msgbytes

# process a message recieved from a client
#def process_message(msgobj, name):
def process_message(message, playername):
    player = players[playername]
    if message['TYPE'] == 'msg':
        # incoming chat message
        chat_msg = message['DATA']
        send_all(bmsg('chatmsg', f'[{datetime.datetime.now()}] {playername}: {chat_msg}'))
    elif message['TYPE'] == 'exit':
        print (f'exit message recieved from {playername}')
        disconnect_client(player)
    elif message['TYPE'] == 'start':
        if not player.ready_start:
            player.ready_start = True
            send_all(bmsg('servermsg', f'{playername} is ready to start'))
        if game.all_players_ready():
            game.start_game()
            send_all(bmsg('start', None))
            send_all(bmsg('gamestat', game.status()))
    elif message['TYPE'] == 'buysell':
        game.process_order(player, message['DATA'])
    else:
        # ERROR
        player.conn.send(bmsg('error', f'Unrecognized message type: {message["DATA"]}'))
        print (f"Got bad message type {message['TYPE']} from {player.name}")
    

# TODO: delete this, not going to be used
def buysell_call(game):
    '''
    Send a message to clients to put in their buysell orders because a market action is
    about to take place
    '''
    if game.buysell_call_id:
        raise RuntimeError("buysell_call issued with one already active")
    call_id = uuid.uuid4()
    game.buysell_call_id = call_id
    send_all(bmsg('buysell', {'reqid': call_id}))

def disconnect_client(player):
    print (f'disconnect_client called for {player.name}')
    with lock: #Unsure how necessary or correct in logic this is...
        #del client_conns[oClient.conn]
        del players[player.name]
        game.remove_player(player.name)
        sel.unregister(player.conn)
        player.conn.close()
    print (f'{player.name} has disconnected')
    send_all(bmsg('disconnect', player.name))
    send_all(bmsg('playerlist', tuple(game.players.keys())))

# msgobj: bytes of json message to send
def send_all(msgobj):
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
                try:
                    msgrec = MessageReceiver('client', conn)
                    msgrec.add_bytes(conn.recv(1024))
                    init_msg = msgrec.get_message()  # blocks
                    print ("initial msg received from connecting client")
                    player_name = init_msg['DATA']
                    if player_name:
                        if player_name in [p.name for p in players.values()]:
                            conn.send(bmsg('error', f'client {player_name} already connected'))
                            print (f'Connection from [{addr}] refused, {player_name} already connected')
                            validconnection = False
                except Exception:
                    print(traceback.format_exc())
                    validconnection = False
                if validconnection:
                    conn.setblocking(False)
                    player = Player(player_name, conn)
                    players[player_name] = player # add to system
                    game.add_player(player)       # add to game
                    sel.register(conn, selectors.EVENT_READ, players[player_name])
                    conn.send(bmsg('conn-accept', None))
                    conn.send(bmsg('initmkt', game.market_summary()))
                    conn.send(bmsg('initplayer', player.summary()))
                    conn.send(bmsg('gamestat', game.status()))
                    send_all(bmsg('joined', player_name))
                    send_all(bmsg('playerlist', tuple(game.players.keys())))
                    print (f'[{player_name}] has joined. {len(players)} total clients')
                else:
                    conn.close()
            else:
                # HMM: when would selectors.EVENT_WRITE ever be used??
                # this is an incoming message from a connected client, or ??
                player = key.data
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    msgrec = player.message_receiver
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
    except KeyboardInterrupt:
        print ('#keyboard interrupt')
        running = False
    except Exception as e:
        print (f'ERROR in main loop: {e}')
        print (traceback.format_exc())
send_all(bmsg('server-exit', None))
serversocket.close()



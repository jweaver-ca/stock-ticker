# (useless comment from andrea)
#
# TODO: .bind localhost <-- need to change for actual network comms to work?
# TODO: handle mutliple rooms, for now just one room for all

import argparse
import socket
#import threading
import selectors
import threading
import traceback
import random # for die rolls
import json
import struct # for predictable integer (message size) encoding to bytes
import datetime
import time
import uuid
import types # SimpleNamespace for stock enum-ish construct?
from st_common import MessageReceiver

parser = argparse.ArgumentParser()
parser.add_argument("-t", "--timersec", type=int, required=False, default=3, help="Default seconds between die rolls")
parser.add_argument("-l", "--gamelen", type=float, required=False, default=15, help="Length of game in minutes")
parser.add_argument("-p", "--port", type=int, required=False, default=8089, help="TCP/IP port to listen for connections")
args = parser.parse_args() 

SERVER_OPT = {
    'timersec': args.timersec,
    'gamelen': args.gamelen
}

# ------------------------------------------------------------------------------
#                              SYNCHRONIZATION NOTES
# ------------------------------------------------------------------------------
# Each players connection runs in its own thread (selector) but a player's
# actions cannot directly affect any game data that is shared by other players.
# 
# A few game actions affect Player attributes (cash (dividend), holdings
# (split,bust) so these actions should be synchronized against Player actions that
# also affect these attributes

# Any buy/sell request from a player depends on stock prices. Market ticks affect
# that so although it's unlikely (e.g. a stock price changes from a market tick
# after a check to see if a player can afford a purchase, so a purchase could get
# made in error resulting in negative cash, etc), all this must be synchronized
# 
# It needs to be guaranteed that no game action initiated by the server can be
# started before the previous game action is complete.  A DiceRollTimer tick does
# not run its action on a separate thread so this happens naturally.

stock = types.SimpleNamespace(GOLD=1,SILVER=2,OIL=3,BONDS=4,INDUSTRIAL=5,GRAIN=6)
stock_names = [ 'GOLD', 'SILVER', 'OIL', 'BONDS', 'INDUSTRIAL', 'GRAIN' ]

sel = selectors.DefaultSelector()

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(('localhost', args.port))
serversocket.listen(5) # become a server socket, maximum 5 connections
#serversocket.settimeout(5) # .accept() blocks and ctrl-c doesn't break out of it.  this allows us to quit easier, but requires us to handle the except during accept

class Client:
    '''Client objects represent a client connected to the server'''
    def __init__(self, name, conn):
        self._name = name
        self.conn = conn
        self.message_receiver = MessageReceiver(f'msgrec-{name}', conn, process_message)
        self.message_receiver.data = name
        self._player = None
        self._game = None

    def get_name(self):
        return self._name

    def get_player(self):
        return self._player

    def get_game(self):
        return self._game

    def set_player_info(self, player):
        self._player = player
        self._game = player.game

    def clear_player_info(self):
        self._player = None
        self._game = None

class Player:
    '''
    Tracks the cash and holdings of a Player in a game. All methods that
    evaluate or alter these should be called from within a section of 
    thread-locked code.  
    
    Methods that are *always* expected to be called from within locked
    section can just use game.assert_locked(). Any method that *could*
    be called either way should provide bln_assert argument to indicate
    if we need to assert game is locked.  (NOTE: this is all just to catch
    bugs)
    '''
    def __init__(self, client, cash, portfolio):
        if client.get_player():
            raise RuntimeError("Cant be a Player in 2 games")
        if not client.game:
            raise RuntimeError("Client should have game property set")
        self.client = client
        self.name = client.get_name()
        self.conn = client.conn # TODO: both Client and Player shouldnt need this
        self._portfolio = [ s for s in portfolio ]
        self.game = client.game
        self.id = str(uuid.uuid4())
        self.cash = cash
        self.ready_start = False

    # cash: amount of cash changed
    # less than zeros should be avoided by application, throw errors here
    def transaction(self, stock, shares, cash):
        # TODO: this is unused, doesn't fit vision. remove
        self._portfolio[stock] += shares
        if self._portfolio[stock] < 0:
            raise ValueError('{self.name} Less than zero shares')
        self.cash += cash
        if self.cash < 0:
            raise ValueError('Less than zero cash')
    
    def add_shares(self, stock, shares):
        self.game.assert_locked()
        if self._portfolio[stock] + shares < 0:
            raise ValueError('{self.name} Less than zero shares [{stock}]')
        self._portfolio[stock] += shares

    def remove_shares(self, stock, shares):
        self.game.assert_locked()
        self.add_shares(stock, -shares)

    def get_portfolio(self, stock=None):
        self.game.assert_locked()
        if stock is None:
            return tuple(self._portfolio)
        else:
            return self._portfolio[stock]

    def set_portfolio(self, stock, newval):
        self.game.assert_locked()
        self._portfolio[stock] = newval

    def set_portfolio_all(self, newvals):
        self.game.assert_locked()
        self._portfolio = [ int(x) for x in newvals ]

    def summary(self):
        '''
        Summary of this player's cash, net worth and market portfolio
        for sending to client
        '''
        portfolio_val = 0
        for i, shares in enumerate(self._portfolio):
            price = self.game.market[i]
            portfolio_val += shares * price
        networth = self.cash + int(portfolio_val/100)
        return {
            'cash': self.cash,
            'networth': networth,
            'portfolio': self.get_portfolio()
        }

class DiceRollTimer(threading.Thread):
    def __init__(self, interval, fn_action):
        '''A StockTickerGame will have a DiceRollTime to control when the dice
        get rolled.

        Market actions in a game should generally run every <interval> seconds.
        When DiceRollTime is first started, it will pause for interval seconds
        and then execute <fn_action()>. This sequence loops forever in its own
        thread.

        If a DiceRollTimer is <pause()>d, action will *not* be executed at
        the end of a countdown, instead it will halt and wait until its <restart()>ed.
        When restarted, the action will fire immediately, then the timer loop will
        continue.

        If DiceRollTimer is paused and restarted again before the end of the first
        paused countdown, it will be like nothing happened the action will fire
        at the same time as if it was never paused at all.
        '''
        super().__init__()
        self.interval = interval
        self.action = fn_action
        self.daemon = True # just die when main thread exits
        self.paused = False
        self.running = False # only False before game start and after game end
        self.restart_event = threading.Event()

    def run(self):
        self.running = True
        while self.running:
            # TODO Timer shouldn't have direct access to send_all. Add a server call. (works fine, just violates concepts)
            send_all(bmsg('actiontime', self.interval))
            time.sleep(self.interval)
            if self.paused:
                self.restart_event.clear()
                self.restart_event.wait()
                # NOTE: if paused, assume when unpaused that all players want die roll immediately
                self.paused = False
            if self.running: # skip action if game has ended
                self.action()

    def pause(self):
        self.paused = True

    def restart(self):
        if self.paused:
            self.paused = False
        if not self.restart_event.is_set():
            self.restart_event.set()

    def stop(self):
        '''stop() is called at the end of the game to stop the DiceRollTimer'''
        self.running = False

    def set_interval(self, seconds):
        self.interval = seconds

class StockTickerGame():
    '''
    Encapsulates an entire session of Stock Ticker including the market
    players.

    StockTickerGame will be limited in time. Number of minutes is adjustable
    via command line argument (--gamelen).  The system time will be stored
    at game start (starttime).  The first die roll that occurs *later* than starttime
    will be the final roll of the game.  Winner will be the player with the highest
    net wealth (the amount of cash after selling the whole portfolio at the final
    prices)
    '''
    STATUS_WAITING_START = 0
    STATUS_RUNNING = 1
    STATUS_ENDED = 2

    def __init__(self, gamename):
        self.INIT_VAL = 100      # stock price for each at game start
        self.OFF_MARKET_VAL = 0  # stock goes off market if <= this price
        self.SPLIT_VAL = 200     # stock will split if >= this price
        self.DIV_VAL = 105       # minimum stock price to pay dividends

        self.INIT_CASH = 5000

        self.STOCK_DIE = tuple(range(len(stock_names))) # should produce 0-5
        self.ACTION_DIE = ('UP', 'DOWN', 'DIV')
        self.AMOUNT_DIE = (5, 10, 20)

        self.name = gamename
        self.id = str(uuid.uuid4())
        self.option_ignore_nopay_divrolls = True # skip die rolls that div a non-paying stock
        self.option_gamelen = SERVER_OPT['gamelen']
        self.option_timer_seconds = SERVER_OPT['timersec']

        #self.stock_names = stock_names hmm not needed
        self.market = [ self.INIT_VAL for i in range(len(stock_names)) ]
        self._players = dict()
        
        # status flags
        # TODO: implement these
        self.status = StockTickerGame.STATUS_WAITING_START
        self.starttime = None # simple unix timestamp
        self.endtime = None
        #self.waiting_to_start = True # becomes False (forever) after starting
        #self.running = False # flag indicating if game underway or not. False before gameplay starts, and after game ends
        #self.has_ended = False # True only after the game has ended

        #self.roll_timer = threading.Timer(self.option_timer_seconds, self.market_action)
        self.roll_timer = DiceRollTimer(self.option_timer_seconds, self.market_action)
        self.game_lock = threading.Lock()
        # REMOVE # self.buysell_call_id = None # id of the last buysell_call sent out to players

    def add_player(self, client):
        if client.get_name() in self._players:
            raise RuntimeError(f"{client.get_name()} already in this game")
        with self.game_lock:
            client.game = self
            p = Player( client, 
                        self.INIT_CASH,
                        tuple(0 for s in stock_names))
            self._players[client.get_name()] = p
            client.set_player_info(p)

    def remove_player(self, playername):
        with self.game_lock:
            client = self._players[playername].client
            client.clear_player_info()
            del self._players[playername]

    def player(self, name):
        return self._players[name]

    def players(self):
        with self.game_lock:
            return tuple(self._players.values())

    def playernames(self):
        with self.game_lock:
            return tuple(self._players.keys())

    def market_summary(self):
        '''
        Get market summary to send to clients/players
        [(stockval, bln_pays_dividend), ... for each stock
        '''
        with self.game_lock:
            return [(val, val>self.DIV_VAL) for val in self.market]

    def all_players_ready(self):
        ''' 
        As players indicate they are ready, this can be checked to see if
        the game should begin.
        '''
        return all([p.ready_start for p in self._players.values()])

    def start_game(self):
        if self.status == StockTickerGame.STATUS_WAITING_START:
            self.status = StockTickerGame.STATUS_RUNNING
            self.starttime = datetime.datetime.now(datetime.timezone.utc)
            self.endtime = self.starttime + datetime.timedelta(minutes=self.option_gamelen)
            self.roll_timer.start()
        else:
            raise RuntimeError(f"Attempt to start_game not in a waiting state {self.status}")

    def die_roll(self):
        ''' Produces a die and returns the result, including a flag to inicate
            if a useless dividend was rolled. Does not act on roll result. '''
        retval = {
            'stock': random.choice(self.STOCK_DIE),
            'action': random.choice(self.ACTION_DIE),
            'amount': random.choice(self.AMOUNT_DIE)
        }
        return retval

    def init_game_info(self, playername):
        p = self._players[playername]
        return { 'cash':      p.cash,
                 'portfolio': p.get_portfolio(),
                 'market':    self.market_summary() }

    def process_order(self, player, buysell_order):
        ''' Apply the buy/sell order '''
        total_cents_spent = 0
        approve_data = {
            'reqid': buysell_order['reqid'],
            'order': [],
            'reject-reason': None
        }
        with self.game_lock:
            new_shares_totals = [ x for x in player.get_portfolio() ]
            for i, (shares, expected_price) in enumerate(buysell_order['data']):
                approve_data['order'].append((shares,self.market[i]))
                total_cents_spent += shares * self.market[i]
                new_shares_totals[i] += shares
            total_dollars_spent = int(total_cents_spent / 100)
            bln_enough_cash = total_dollars_spent <= player.cash
            bln_enough_shares = all((s>=0 for s in new_shares_totals)) 
            if bln_enough_cash and bln_enough_shares:
                player.cash -= total_dollars_spent
                player.set_portfolio_all(new_shares_totals)
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
            approve_data['portfolio'] = player.get_portfolio()
        player.conn.send(bmsg('approve', approve_data))
        
    def _process_split(self, i_stock):
        '''
        Stock prices reached max. Process dividend, reset price, adjust affected player
        portfolios, return messages.

        Must be called with the game_lock on.
        '''
        self.assert_locked()
        if not self.game_lock.locked():
            # NOTE: *could* use re-entrant lock but prefer to avoid
            raise RuntimeError("Unsynchronized call")

        player_msgs = []
        for player in self._players.values():
            # dividend 20 paid out
            div_dollars = int(player.get_portfolio(i_stock) * 0.2)
            player.cash += div_dollars
            shares_gained = player.get_portfolio(i_stock)
            player.add_shares(i_stock, shares_gained)
            split_msg_data = {
                'stock': i_stock,
                'newprice': self.INIT_VAL,
                'div': self.INIT_VAL >= self.DIV_VAL, # always no after split
                'shares': player.get_portfolio(i_stock),
                'gained': shares_gained,
                'divpaid': div_dollars,
                'playercash': player.cash
            }
            player_msgs.append((player, bmsg('split', split_msg_data)))
        self.market[i_stock] = self.INIT_VAL
        return player_msgs
        
    def _process_bust(self, i_stock):
        '''
        Stock prices reached zero. Reset price, adjust affected player
        portfolios, return generated messages.

        Must be called with the game_lock on.
        '''
        self.assert_locked()

        player_msgs = []
        for player in self._players.values():
            shares_lost = player.get_portfolio(i_stock)
            player.set_portfolio(i_stock, 0)
            bust_msg_data = {
                'stock': i_stock,
                'newprice': self.INIT_VAL,
                'div': self.INIT_VAL >= self.DIV_VAL,
                'shares': 0,
                'lost': shares_lost
            }
            player_msgs.append((player, bmsg('offmarket', bust_msg_data)))
        self.market[i_stock] = self.INIT_VAL
        return player_msgs

    def market_action(self):
        '''Rolls dice and applies changes to the game (DiceRollTimer's action)
        This is the target of the DiceRollTimer. Also checks the time to see
        if the game has ended'''
        # roll the dice
        player_msgs = [] # send after lock released
        with self.game_lock:
            roll = self.die_roll()
            attempts = 1
            max_attempts = 100
            if self.option_ignore_nopay_divrolls:
                while self.roll_div_unpaid(roll) and attempts < max_attempts:
                    if attempts == max_attempts:
                        raise RuntimeError(f"Too many no-pay dividend die rolls")
                    attempts += 1
                    roll = self.die_roll()
            player_msgs.extend((p, bmsg('roll', roll)) for p in self._players.values())
            price_change_data = None
            # simplify reading roll values
            (stock, action, amount) = (roll[x] for x in ['stock', 'action', 'amount'])
            if action in ['UP', 'DOWN']:
                self.market[stock] += amount if action=='UP' else -amount
                split_bust_msgs = None
                if self.market[stock] >= self.SPLIT_VAL:
                    split_bust_msgs = self._process_split(stock)
                elif self.market[stock] <= self.OFF_MARKET_VAL:
                    split_bust_msgs = self._process_bust(stock)
                price_change_data = {'stock': stock,
                        'amount': amount,
                        'newprice': self.market[stock],
                        'div': self.pays_dividend(stock)
                    }
                pc_msg = bmsg('markettick', price_change_data)
                # market_tick messages should go before split/bust
                player_msgs.extend((p, pc_msg) for p in self._players.values())
                if split_bust_msgs:
                    player_msgs.extend(split_bust_msgs)
            if action == 'DIV' and self.pays_dividend(stock):
                for player in self._players.values():
                    div_dollars = int(player.get_portfolio(stock) * amount/100)
                    if div_dollars:
                        player.cash += div_dollars
                        div_msg_data = {
                            'stock': stock,
                            'amount': amount,
                            'divpaid': div_dollars,
                            'playercash': player.cash
                        }
                        player_msgs.append((player, bmsg('div', div_msg_data)))
            # check time
            curtime = datetime.datetime.now(datetime.timezone.utc)
            if curtime > self.endtime:
                # game is over, set status, stop timer while locked
                self.status = StockTickerGame.STATUS_ENDED
                self.roll_timer.stop()

            # end lock
        for (p, m) in player_msgs:
            p.conn.send(m)
        if self.status == StockTickerGame.STATUS_ENDED:
            self.end_game()

    def pays_dividend(self, i_stock):
        self.assert_locked()
        return self.market[i_stock] >= self.DIV_VAL

    def roll_div_unpaid(self, roll):
        ''' returns True IFF action is 'DIV' but stock doesn't pay '''
        self.assert_locked()
        return roll['action'] == 'DIV' and not self.pays_dividend(roll['stock'])

    def assert_locked(self):
        '''assert_locked: called by functions that don't want to obtain the game_lock
        themselves, but must always be called from code blocks that have the game_lock
        already. (a mechanism to help prevent buggy programming)
        '''
        if self.is_running() and not self.game_lock.locked():
            raise RuntimeError("Game is not locked")

    def is_running(self):
        return self.status == StockTickerGame.STATUS_RUNNING

    def end_game(self):
        '''Figure out the winner, send messages'''
        max_networth = -1
        winners = []
        lst_player_data = []
        for p in self.players():
            summary = p.summary() 
            summary['name'] = p.name
            lst_player_data.append(summary)
            if summary['networth'] > max_networth:
                max_networth = summary['networth']
                winners = [p.name]
            elif summary['networth'] == max_networth:
                winners.append(p.name)
        end_game_data = {
            'winner': winners,
            'winner-networth': max_networth,
            'player-info': lst_player_data
        }
        send_all(bmsg('gameover', end_game_data))

    def get_status(self):
        # NOTE: may add more details (e.g. paused,etc?), so using dictionary even though just 1 item...
        '''Current game status. 
        return value here is used as the value in a 'gamestat' message to clients
        '''
        if self.status == StockTickerGame.STATUS_WAITING_START:
            return 'WAITING-START'
        elif self.status == StockTickerGame.STATUS_RUNNING:
            return 'RUNNING'
        elif self.status == StockTickerGame.STATUS_RUNNING:
            return 'ENDED'
        else:
            raise ValueError(f"Game in bad state: {self.status}")

# -- end class StockTickerGame

# NOTE: any use for supplying data here? Example in python selectors web page did...
sel.register(serversocket, selectors.EVENT_READ, "listen-new")

# NOTE: One day server will be able to host multiple games so conceptually keeping
#       the design such that the change will be easier
games = dict()

def create_game(name):
    if name in games:
        raise ValueError(f"game already exists [{name}]")
    games[name] = StockTickerGame(name)

# Until clients can create games, make one
create_game('default-game')
game = StockTickerGame('default-game')
clients = dict()  # key = player name. *all* players in system

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

def process_join_request(client, gamename, gid):
    ''' client message: join-game 
        return True if successful'''
    if client.get_player():
        return (False, 'already in a game')
    if not gamename in games:
        return (False, 'game not found')
    game = games[gamename]
    if gid != game.id:
        return (False, 'wrong game id')
    game.add_player(client)
    return (True, None)

# process a message recieved from a client
#def process_message(msgobj, name):
def process_message(message, clientname):
    mtype, mdata = message['TYPE'], message['DATA']
    client = clients[clientname]
    player = client.get_player()
    game = client.get_game()
    try:
        if message['TYPE'] == 'msg':
            # incoming chat message
            chat_msg = message['DATA']
            #send_all(bmsg('chatmsg', f'[{datetime.datetime.now()}] {clientname}: {chat_msg}'))
            send_all(bmsg('chatmsg', {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'playername': clientname,
                        'message': chat_msg}))
        elif message['TYPE'] == 'exit':
            print (f'exit message recieved from {clientname}')
            disconnect_client(client)
        elif message['TYPE'] == 'join-game':
            gamename, gid = mdata
            bln_success, fail_reason = process_join_request(client, gamename, gid)
            if bln_success:
                # success - send game info
                game = games[gamename]
                player = game.player(client.get_name())
                client.conn.send(bmsg('initgame', game.init_game_info(player.name)))
                client.conn.send(bmsg('gamestat', game.get_status()))
                send_all(bmsg('joined', {'newplayer': player.name, 'all': game.playernames()}))
                client.conn.send(bmsg('playerlist', game.playernames()))
            else:
                # fail
                client.conn.send(bsmg('joinfail', {'reason': fail_reason}))
                
        elif message['TYPE'] == 'readystart':
            if not player.ready_start:
                player.ready_start = True
                send_all(bmsg('servermsg', f'{player.name} is ready to start'))
            if game.all_players_ready():
                game.start_game()
                send_all(bmsg('gamestart', {
                        'gamelen': game.option_gamelen, 
                        'stoptime': game.endtime.isoformat()}))
                send_all(bmsg('gamestat', game.get_status()))
        elif message['TYPE'] == 'buysell':
            game.process_order(player, message['DATA'])
        else:
            # ERROR
            client.conn.send(bmsg('error', f'Unrecognized message type: {message["DATA"]}'))
            print (f"Got bad message type {message['TYPE']} from {clientname}")
    except:
        client.conn.send(bmsg('error', f'Message Processing caused exception: {mtype} | {mdata}'))
        print (f'Message from {clientname} caused exception: {mtype} | {mdata}')
        print(traceback.format_exc())
    

# NOTE: not used in the current version of the game. Could be a future option
def buysell_call(game):
    '''
    Send a message to clients to put in their buysell orders because a market action is
    about to take place
    UNUSED - this might be part of a game option in the future
    '''
    if game.buysell_call_id:
        raise RuntimeError("buysell_call issued with one already active")
    call_id = uuid.uuid4()
    game.buysell_call_id = call_id
    send_all(bmsg('buysell', {'reqid': call_id}))

def disconnect_client(client):
    name = client.get_name()
    print (f'disconnect_client called for {name}')
    #del client_conns[oClient.conn]
    if game := client.get_game():
        game.remove_player(name) # call is sync'd
        send_all_game(game, bmsg('disconnect', name))
        send_all_game(game, bmsg('playerlist', game.playernames()))
        print (f'Removed {name} from game "{game.name}"')
    sel.unregister(client.conn)
    client.conn.close()
    del clients[name]
    print (f'{name} has disconnected')

# msgobj: bytes of json message to send
def send_all(msgobj):
    for client in clients.values():
        client.conn.send(msgobj)

def send_all_game(game, msgobj):
    for player in game.players():
        player.conn.send(msgobj)

def send_others_game(player, msgobj):
    if player.game is None:
        # TODO: add better error handling
        print (f"ERROR! send_others_game for {player.name}. Not in game")
    for o_player in player.game.players():
        if o_player.name != player.name:
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
                    #NOTE: first MessageReceiver uses get_message, the next one uses a handler
                    msgrec = MessageReceiver('client', conn)
                    msgrec.add_bytes(conn.recv(1024))
                    init_msg = msgrec.get_message()  # blocks
                    if init_msg['TYPE'] != 'initconn':
                        # TODO: something more meaningful here
                        print (f'Bad message type [{init_msg["TYPE"]}] from [{addr}]')
                    else:
                        print ("initial msg received from connecting client")
                    client_name = init_msg['DATA']
                    if client_name:
                        if client_name in clients:
                            conn.send(bmsg('error', f'Client {client_name} already connected'))
                            print (f'Connection from [{addr}] refused, {client_name} already connected')
                            validconnection = False
                except Exception:
                    print(traceback.format_exc())
                    validconnection = False
                if validconnection:
                    conn.setblocking(False)
                    client = Client(client_name, conn)
                    clients[client_name] = client # add to system
                    # MOVE THIS: game.add_player(player)       # add to game
                    sel.register(conn, selectors.EVENT_READ, clients[client_name])
                    # send list of game names
                    # TODO: only list games that are joinable/not started
                    conn.send(bmsg('conn-accept', tuple((g.name,g.id) for g in games.values())))
                    print (f'[{client_name}] has joined. {len(clients)} total clients')
                else:
                    conn.close()
            else:
                # HMM: when would selectors.EVENT_WRITE ever be used??
                # this is an incoming message from a connected client
                client = key.data
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    msgrec = client.message_receiver
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
                        disconnect_client(client)
    except KeyboardInterrupt:
        print ('#keyboard interrupt')
        running = False
    except Exception as e:
        print (f'ERROR in main loop: {e}')
        print (traceback.format_exc())
send_all(bmsg('server-exit', None))
serversocket.close()



# TODO: ensure easy way to exit
# TODO: exit properly on error
# v2 add selectors
# V3:
# - add message objects
# - allow server to send shutdown requests to clients
# - handle client disconnect by server

import argparse
import traceback
import socket
import threading
import selectors
import json
import struct
import datetime
import types # SimpleNamespace for stock enum-ish construct?
from st_gameboard import GameBoard
from st_common import MessageReceiver

try:
    import curses
except ModuleNotFoundError:
    # once installed on system, this all goes away
    print ("[curses] library not installed.")
    print ("try > pip install windows-curses")
    exit (1)


default_args = {
    'port': 8089,
    'server': 'localhost'
}
parser = argparse.ArgumentParser()
parser.add_argument("--name", "-n", help="Chat name")
parser.add_argument("--server", "-s", default=default_args['server'], help=f"IP/URL of stock ticker game server (default: {default_args['server']})")
parser.add_argument("--port", "-p", type=int, default=default_args['port'], help=f"Port of stock ticker game server (default: {default_args['port']})")

args = parser.parse_args() 
gameserver = args.server

# game rules TODO: these should come from the server
# in any case, these value MUST match the server...
DIV_MIN = 105 # minimum stock value to pay dividends
SPLIT_VAL = 200 # when a stock reachese this value it splits
BUST_VAL = 0    # stock goes "off the market" if at or below this value
INIT_VAL = 100  # price each stock starts at

# Could use Enum.. no real need I think...
# TODO: decide if simplenamespace or just a plain old array of string for stocks...
stock_names = [ 'GOLD', 'SILVER', 'INDUSTRIAL', 'BONDS', 'OIL', 'GRAIN' ]
stock = types.SimpleNamespace(GOLD=1,SILVER=2,INDUSTRIAL=3,BONDS=4,OIL=5,GRAIN=6)

class Player:
    def __init__(self, name):
        self.name = name
        self.portfolio = [ 0 for i in range(len(stock_names)) ]
        self.cash = 0
        self.initialized = False # server needs to send info before use
        self.ready_start = False

class StockMarket:
    def __init__(self):
        self.prices = None
        self.initialized = False # server needs to send info before use

    def shareprice(self, i_stock):
        if not self.initialized:
            raise RuntimeError(f"StockMarket not initialized")
        return self.prices[i_stock]

class ClientGame:
    def __init__(self, player, market):
        self.player = player
        self.market = market

# simple message object/dictionary
# TODO: rename msg because it shares name with message type 'msg' / confusing
def msg(strType, strData):
    return {'TYPE': strType, 'DATA': strData}

# shortcut to get bytes (utf-8) of json-encoded message, including 4 byte size
# result from this function can go right into socket.send(...)
def bmsg(strType, strData):
    msgbytes = json.dumps(msg(strType, strData)).encode('utf-8')
    sz = len(msgbytes)
    return struct.pack('I', sz) + msgbytes

# called by client once completed message received from server
def process_message(msgobj):
    global running
    global gameboard
    #msgobj = oClient.message
    if msgobj['TYPE'] == 'chatmsg':
        #globalscr.addstr(msgobj['DATA'] + '\n')
        gameboard.add_system_msg(msgobj['DATA'])
    elif msgobj['TYPE'] == 'error':
        gameboard.add_system_msg(f'ERROR FROM SERVER: {msgobj["DATA"]}\n')
        running = False
    elif msgobj['TYPE'] == 'conn-accept':
        gameboard.add_system_msg("** connection to server accepted **\n")
    elif msgobj['TYPE'] == 'disconnect':
        gameboard.add_system_msg(f'[{msgobj["DATA"]} has disconnected]\n')
    elif msgobj['TYPE'] == 'joined':
        gameboard.add_system_msg(f'[{msgobj["DATA"]} has joined]\n')
    elif msgobj['TYPE'] == 'server-exit':
        gameboard.add_system_msg(f'[SERVER SHUTDOWN! Exiting...]\n')
        running = False
    elif msgobj['TYPE'] == 'initmkt':
        update_market(msgobj['DATA'])
    elif msgobj['TYPE'] == 'playerlist':
        update_players(msgobj['DATA'])
    elif msgobj['TYPE'] == 'gamestat':
        update_game_status(msgobj['DATA'])
    elif msgobj['TYPE'] == 'actiontime':
        # TODO: animate the countdown timer
        pass
        #gameboard.add_system_msg(f'Countdown to roll started: {msgobj["DATA"]}')
    elif msgobj['TYPE'] == 'roll':
        gameboard.display_die_roll(msgobj['DATA'])
    elif msgobj['TYPE'] == 'market':
        d = msgobj['DATA']
        gameboard.update_stock_price(d['stock'], d['newprice'], d['div'])
    elif msgobj['TYPE'] == 'split':
        gameboard.display_split_message(msgobj['DATA'])
    elif msgobj['TYPE'] == 'offmarket':
        gameboard.display_bust_message(msgobj['DATA'])
    elif msgobj['TYPE'] == 'initplayer':
        update_player(msgobj['DATA'])
    elif msgobj['TYPE'] == 'start':
        gameboard.add_system_msg('All players ready. Game has started!')
    elif msgobj['TYPE'] == 'servermsg':
        gameboard.add_system_msg(str(msgobj['DATA']))
        # TODO set any flags here to allow gameplay
    else:
        raise ValueError(f"unknown message type received: [{msgobj['TYPE']}] data:{msgobj['DATA']}")

# globals TODO: is there a better way?
running = True
player = None # NOTE/TODO: not sure how necessary it is to keep client copies of player/market
market = None # [ (stockval, bln_dividend), (stockval, bln_dividend), etc ]
gameboard = None
clientsocket = None

# TODO: clientsocket is global. probably not great
# NOTE: since select() is hard/impossible to interrupt without timeout, maybe the solution
#   is to send/recieve a final message
# Send a note to server that we are disconnecting.
# NOTE: the close() call on the socket should *ONLY* be done when a 0-byte read message has been
#    received from the server... right??  What about if the *server* initiates the shut-down?

# NOTE: while main is executing wrapped in curses.wrapper I can't seem to get access to
#   exceptions thrown within main.  curses handles them all, which means I can't use
#   signal.raise from withing the keyboard thread to interrupt selector.select()

# NOTE: selectors says if a signal is received in the thread  where .select() is block
#   it might just return an empty list

def process_gameboard_ops(gameboard):
    while running:
        op = gameboard.get_operation(block=True, timeout=2) # blocking
        if op is None:
            continue # timeout reached
        if op['TYPE'] == 'chat-message':
            send_chat_message(op['DATA'])
        elif op['TYPE'] == 'quit':
            process_quit()
        elif op['TYPE'] == 'ready-start':
            if not player.ready_start:
                clientsocket.send(bmsg('start', op['DATA']))
                player.ready_start = True
            else:
                gameboard.dbg('game start requested again')
        else:
            gameboard.add_system_msg('ERROR: bad game operation type: {op["TYPE"]}')

def send_chat_message(str_message):
    clientsocket.send(bmsg('msg', str_message))

def process_quit():
    clientsocket.send(bmsg('exit', None))
    running = False

def update_market(market_summary):
    for i, (stockval, bln_div) in enumerate(market_summary):
        gameboard.update_stock_price(i, stockval, bln_div)
        market = market_summary

def update_players(playerlist):
    other_player_list = [ name for name in playerlist if name != args.name ]
    gameboard.update_players(args.name, other_player_list)

def update_game_status(game_status):
    # NOTE: I think it makes sense for this to be a simple string from client to gameboard
    # A status message typically is just a plain string
    str_status = f'[Connected to {args.server}]'
    if game_status['started']:
        str_status += ' Game started'
    else:
        str_status += ' Waiting for game start'
    gameboard.update_status(str_status)

def update_player(player_status):
    gameboard.update_player(player_status)
    player.cash = player_status['cash']
    player.portfolio = player_status['portfolio']
    player.initialized = True # set flag that player object is ready to use 
    # NOTE: networth is basically useless here? it's just for diplay IMO
    
#try:
def main(stdscr):
    curses.curs_set(0)
    
    global gameboard
    global player
    global market
    global running
    global clientsocket

    gameboard = GameBoard(stdscr, stock_names)
    gameboard.debug = True
    gameboard.redraw() # TODO: I think this is unnecessary, remove and make sure no screen drawing errors creep in

    gameboard_thread = threading.Thread(target=process_gameboard_ops, args=(gameboard,))
    gameboard_thread.start()

    player = Player(args.name)
    market = None

    # --------------------------------------------------------
    # Attempt connecton to game server
    # --------------------------------------------------------
    try:
        clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        clientsocket.connect((gameserver, args.port))
    except:
        print (f"Connection to [{gameserver}] failed")
        exit (1)
    # MessageReceiver is duplicate of that found in chat_server_v3.py, so just give name 'server'
    # msgrec is attached to selector and will simply process messages from the server
    msgrec = MessageReceiver('server', clientsocket, process_message)
    #clientsocket.send(bytes(args.name, 'UTF-8'))
    clientsocket.send(bmsg('initconn',args.name))

    sel = selectors.DefaultSelector()
    #sel.register(clientsocket, selectors.EVENT_READ | selectors.EVENT_WRITE, None)
    sel.register(clientsocket, selectors.EVENT_READ, None)


    # TODO: At this point, GameBoard's thread has started (on __init__) but this main thread has no way to react
    #     to keypresses in the GameBoard because this thread gets tied up below with select() calls
    #     Is the solution to put the selector in its own thread and somehow have another
    #     loop running as the main thread?  what would that look like?
    # IDEA: since this main thread is tied up if and only if (right?) the connection to the server
    #     is intact, we could send the server a message that we want to quit, and the server could
    #     send us a message which would end the block.  STUPID, RIGHT?
    # IDEA: do we just give up and put select() on a timeout?? what is wrong with that?
    #       > is it just the using of resources??

    # IDEA: Use threading.Event in GameBoard to send events to the client game instead of sending the
    #     GameBoard an object with an API for the client.  This would mean the client thread is in charge
    #     executing requests made by user through the GameBoard, instead of GameBoard/Keyboard thread 
    #     executing game operations through the client API.  Advantage is the client data structures
    #     don't need to be synchronized anymore. Instead the queue of of user input requests would need
    #     to be synchronized.
    # THOUGHT: there are situations where input could be made on the GameBoard that isn't valid based
    #     on the current game state e.g. Issue a buy order, but the client has sent the buy order to server
    #     for processing and we are awaiting the results (which would mean there is a market activity 
    #     imminent and so we won't know what the stock prices are).  The GameBoard should try to limit
    #     this through UI, but it can't be perfect.  SO WHICH WAY ADDRESSES THIS ISSUE BEST?

    # NOTE: main thread runs the selector loop
    # NOTE: KeyboardThread runs the curses input loop

    #kt = KeyboardThread(args.name, stdscr, clientsocket)
    #kt.start()
    # TODO: this is bad OOP... adding kt to msgrec...
    # msgrec.kt = kt
    while running:
        # select() seems to be interruptable by KeyboardInterrupt
        try:
            events = sel.select(timeout=1.0)
            #events = sel.select()
            for key, mask in events:
                conn = key.fileobj
                if mask & selectors.EVENT_READ:
                    b = conn.recv(1024)
                    if b:
                        msgrec.add_bytes(b)
                    else:
                        # disconnect?
                        print ('Server disconnected')
                        msgrec.conn.close()
                        running = False
        except:
            gameboard.program_exited = True
            running = False
            print(traceback.format_exc())
    print ('end main: ' + str(datetime.datetime.now()))
#clientsocket.close() # TODO: is it harmless to close again? check what purpose does it serve?
#finally:
#print ('finally: ' + str(datetime.datetime.now()))
#   stdscr.keypad(False)
#   curses.nocbreak()
#   curses.echo()
#   curses.endwin()

if __name__ == '__main__':
    curses.wrapper(main)
    print ('final exit')

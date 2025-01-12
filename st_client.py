# TODO: ensure easy way to exit
# TODO: exit properly on error
# v2 add selectors
# V3:
# - add message objects
# - allow server to send shutdown requests to clients
# - handle client disconnect by server

import argparse
import socket
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

# Could use Enum.. no real need I think...
# TODO: decide if simplenamespace or just a plain old array of string for stocks...
stock_names = [ 'GOLD', 'SILVER', 'INDUSTRIAL', 'BONDS', 'OIL', 'GRAIN' ]
stock = types.SimpleNamespace(GOLD=1,SILVER=2,INDUSTRIAL=3,BONDS=4,OIL=5,GRAIN=6)

class StockTickerClient():
    '''
    This we passed to the GameBoard so that it can make calls here e.g.
    send a chat message, request stock purchase etc.
    '''
    def __init__(self, socket):
        self.socket = socket

    def send_chat_message(self, str_message):
        self.socket.send(bmsg('msg', str_message))

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

# globals TODO: is there a better way?
running = True
gameboard = None

# process keyboard instruction to quit.
# TODO: clientsocket is global. probably not great
# NOTE: since select() is hard/impossible to interrupt without timeout, maybe the solution
#   is to send/recieve a final message
# Send a note to server that we are disconnecting.
# NOTE: the close() call on the socket should *ONLY* be done when a 0-byte read message has been
#    received from the server... right??  What about if the *server* initiates the shut-down?
def disconnect():
    msgrec.conn.send(bmsg('exit', None))
    msgrec.conn.shutdown(socket.SHUT_WR)
    #msgrec.conn.close()

# NOTE: while main is executing wrapped in curses.wrapper I can't seem to get access to
#   exceptions thrown within main.  curses handles them all, which means I can't use
#   signal.raise from withing the keyboard thread to interrupt selector.select()

# NOTE: selectors says if a signal is received in the thread  where .select() is block
#   it might just return an empty list

#try:
def main(stdscr):
    
    global gameboard
    global running

    oClient = StockTickerClient(clientsocket)
    gameboard = GameBoard(stdscr, stock_names, oClient)
    gameboard.debug = True
    gameboard.redraw()

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
        except Exception as e:
            print ('main Exception start: ' + str(datetime.datetime.now()))
            gameboard.dbg(f"interrupt: {e}\n")
            print(f"interrupt: {e}")
            running = False
        if gameboard.has_exited():
            running = False
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

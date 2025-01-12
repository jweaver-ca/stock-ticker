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
import signal # trying to get KeyboardThread to interrupt main thread
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



# simple message object/dictionary
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
    global globalscr
    #msgobj = oClient.message
    if msgobj['TYPE'] == 'chatmsg':
        globalscr.addstr(msgobj['DATA'] + '\n')
    elif msgobj['TYPE'] == 'error':
        globalscr.addstr(f'ERROR FROM SERVER: {msgobj["DATA"]}\n')
        running = False
    elif msgobj['TYPE'] == 'conn-accept':
        globalscr.addstr("** connection to server accepted **\n")
    elif msgobj['TYPE'] == 'disconnect':
        globalscr.addstr(f'[{msgobj["DATA"]} has disconnected]\n')
    elif msgobj['TYPE'] == 'joined':
        globalscr.addstr(f'[{msgobj["DATA"]} has joined]\n')
    elif msgobj['TYPE'] == 'server-exit':
        globalscr.addstr(f'[SERVER SHUTDOWN! Exiting...]\n')
        running = False
    globalscr.refresh()


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

running = True
globalscr = None

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
    
    global globalscr
    global running

    gb = GameBoard(stdscr, stock_names)
    globalscr = stdscr

#   stdscr.border()
#   chatscr = stdscr.derwin(curses.LINES-4,1)
#   chatscr.border()
#   stdscr.addstr('this is stdscr\n')
#   chatscr.addstr(1, 1, 'this is chatscr', curses.A_REVERSE)
#   chatscr.addstr(2, 1, 't2his is chatscr', curses.A_REVERSE)
#   chatscr.noutrefresh()
#   stdscr.noutrefresh()
#   curses.doupdate()
#   chatscr.getch()

    # NOTE: main thread runs the selector loop
    # NOTE: KeyboardThread runs the curses input loop

    kt = KeyboardThread(args.name, stdscr, clientsocket)
    kt.start()
    # TODO: this is bad OOP... adding kt to msgrec...
    msgrec.kt = kt
    while running:
        # select() seems to be interruptable by KeyboardInterrupt
        try:
            #events = sel.select(timeout=1.0)
            events = sel.select()
            print (f"select() done. {events}")
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
            stdscr.addstr (f"interrupt: {e}\n")
            print(f"interrupt: {e}")
            stdscr.refresh()
            running = False
    kt.stop()
    print ('end main: ' + str(datetime.datetime.now()))
#clientsocket.close() # TODO: is it harmless to close again? check what purpose does it serve?
#finally:
#print ('finally: ' + str(datetime.datetime.now()))
#   stdscr.keypad(False)
#   curses.nocbreak()
#   curses.echo()
#   curses.endwin()

curses.wrapper(main)
print ('final exit')

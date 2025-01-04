# TODO: ensure easy way to exit
# TODO: exit properly on error

import argparse
import socket
import threading
import selectors
try:
    import curses
except ModuleNotFoundError:
    # once installed on system, this all goes away
    print ("[curses] library not installed.")
    print ("try > pip install windows-curses")
    exit (1)


parser = argparse.ArgumentParser()
parser.add_argument("name", help="Chat name")

args = parser.parse_args() 

clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientsocket.connect(('localhost', 8089))
clientsocket.send(bytes(args.name, 'UTF-8'))

sel = selectors.DefaultSelector()
#sel.register(clientsocket, selectors.EVENT_READ | selectors.EVENT_WRITE, None)
sel.register(clientsocket, selectors.EVENT_READ, None)

running = True

class KeyboardThread(threading.Thread):
    def __init__(self, name, scr, conn):
        super().__init__(name=name)
        self.scr = scr
        self.conn = conn
        self.msg = ""
        self.daemon = True
        self.running = False

    def run(self):
        global curses
        self.running = True
        while self.running:
            if self.running:
                val = self.scr.getch() # blocking (since curses.nodelay() not called)
                if val in [curses.KEY_ENTER, 10, 13]:
                    if self.msg:
                        self.conn.send(bytes(self.msg, 'utf-8'))
                        self.scr.addstr(f'\nSending: {self.msg}\n')
                        self.msg = ""
                        self.scr.refresh()
                elif val in [curses.KEY_BREAK, curses.KEY_DOWN]:
                    running = False
                    break
                else:
                    self.msg += chr(val)
                    self.scr.addstr(chr(val))
                    self.scr.refresh()
                #self.scr.addstr(str(val)) # just print the # to the screen
                #self.scr.refresh()
            else:
                # shutdown indicated from somewhere
                pass
    def stop():
        self.running = False

def main(stdscr):
    kt = KeyboardThread(args.name, stdscr, clientsocket)
    kt.start()
    while running:
        events = sel.select()
        for key, mask in events:
            blnread, blnwrite = (mask & selectors.EVENT_READ,mask & selectors.EVENT_WRITE)
            conn = key.fileobj
            if mask & selectors.EVENT_READ:
                buf = conn.recv(1024)
                if buf ==  SHUTDOWN FROM SERVER:
                    if kt.is_alive():
                        stdscr.addstr('SHUTDOWN. Press any key to exit')
                    else:
                        stdscr.addstr('SHUTDOWN')
                    # 
                    kt.stop()
                    running = False
                else:
                    stdscr.addstr(buf.decode() + '\n')
                    stdscr.refresh()

curses.wrapper(main)
running = False

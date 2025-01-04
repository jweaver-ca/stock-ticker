# TODO: ensure easy way to exit
# TODO: exit properly on error

import argparse
import socket
import threading
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

class KeyboardThread(threading.Thread):
    def __init__(self, name, scr, conn):
        super().__init__(name=name)
        self.scr = scr
        self.conn = conn
        self.msg = ""

    def run(self):
        global curses
        while True:
            val = self.scr.getch() # blocking (since curses.nodelay() not called)
            if val in [curses.KEY_ENTER, 10, 13]:
                if self.msg:
                    self.conn.send(bytes(self.msg, 'utf-8'))
                    self.scr.addstr(f'\nSending: {self.msg}\n')
                    self.msg = ""
                    self.scr.refresh()
            elif val in [curses.KEY_BREAK, curses.KEY_DOWN]:
                break
            else:
                self.msg += chr(val)
                self.scr.addstr(chr(val))
                self.scr.refresh()
            #self.scr.addstr(str(val)) # just print the # to the screen
            #self.scr.refresh()

def main(stdscr):
    kt = KeyboardThread(args.name, stdscr, clientsocket)
    kt.start()
    kt.join()

curses.wrapper(main)

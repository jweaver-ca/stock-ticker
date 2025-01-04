# stockticker-server.py

import argparse
import sys
import socket
import selectors
import types
from enum import Enum
import random

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port",help="IP Port to listen on.", default = 11123)
args = parser.parse_args()

sel = selectors.DefaultSelector()
select_timeout = 10 # 10 while developing to make keyboard interrupts easier

class Stock(Enum):
    GOLD = 1
    SILVER = 2
    BONDS = 3
    OIL = 4
    INDUSTRIAL = 5
    GRAIN = 6

class GameRuleException(Exception):
    pass

class StockMarket:
    def __init__(self):
        self.SPLITVAL = 200
        self.DIVVAL = 105
        self.INITVAL = 100
        self.shareprice = {
            Stock.GOLD: self.INITVAL,
            Stock.SILVER: self.INITVAL,
            Stock.BONDS: self.INITVAL,
            Stock.OIL: self.INITVAL,
            Stock.INDUSTRIAL: self.INITVAL,
            Stock.GRAIN: self.INITVAL
        }
    
    def roll(self):
        stock = random.choice([i for i in Stock])
        action = random.choice(['UP', 'DOWN', 'DIV'])
        amount = random.choice([5, 10, 20])
        print (f"{stock.name} {action} {amount}")
        if action == 'UP':
            self.shareprice[stock] += amount
            # check for split
        elif action == 'DOWN':
            self.shareprice[stock] -= amount
            # check for bust
        elif action == 'DIV':
            if self.shareprice[stock] >= self.DIVVAL:
                print ("PAID!")

class Game:
    def __init__(self):
        self.market = StockMarket()
        self.players = dict()
        self.SHAREBLOCKSIZE = 500 # shares are bought/sold in groups this big

    def __repr__(self):
        retval = ','.join([f"{name}:{self.market.shareprice[x]}" for name,x in Stock.__members__.items() ])
        for name, p in self.players.items():
            retval += f"\n{p}"
        return retval

    def add_player(self, name):
        self.players[name] = Player(name)

    # shares > 0 means BUY
    def trade(self, player, stock, shares):
        if shares % self.SHAREBLOCKSIZE != 0:
            raise GameRuleException(f"# shares not divisible by {self.SHAREBLOCKSIZE}")
        cost = int(shares * self.market.shareprice[stock] / 100)
        if shares > 0 and cost > player.cash:
            raise GameRuleException(f"Player {player.name} can't afford the purchase")
        if player.portfolio[stock] + shares < 0:
            raise GameRuleException(f"Player {player.name} doesn't have enough shares")
        player.portfolio[stock] += shares
        player.cash -= cost
        

class Player:
    def __init__(self, name, startcash = 5000):
        self.name = name
        self.cash = startcash
        self.portfolio = {s: 0 for s in Stock}

    def __repr__(self):
        retval = f"{self.name}: ${self.cash:d} "
        retval += ",".join([f"{s.name}: {self.portfolio[s]}" for s in Stock if self.portfolio[s] > 0])
        return retval

def accept_wrapper(sock):
    conn, addr = sock.accept()  # Should be ready to read
    print(f"Accepted connection from {addr}")
    conn.setblocking(False)
    data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(conn, events, data=data)

def service_connection(key, mask):
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ:
        recv_data = sock.recv(1024)  # Should be ready to read
        if recv_data:
            data.outb += recv_data
        else:
            print(f"Closing connection to {data.addr}")
            sel.unregister(sock)
            sock.close()
    if mask & selectors.EVENT_WRITE:
        if data.outb:
            print(f"Echoing {data.outb!r} to {data.addr}")
            sent = sock.send(data.outb)  # Should be ready to write
            data.outb = data.outb[sent:]

host, port = '127.0.0.1', int(args.port)
lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
lsock.bind((host, port))
lsock.listen()
print(f"Listening on {(host, port)}")
lsock.setblocking(False)
sel.register(lsock, selectors.EVENT_READ, data=None)

game = Game()
print (game)
game.add_player("George")
game.add_player("Bill")
game.trade(game.players["Bill"], Stock.GOLD, 500)
game.trade(game.players["George"], Stock.INDUSTRIAL, 1000)
for i in range(10):
    game.market.roll()
    print (game)
#print (game.market.shareprice[Stock.GOLD])
#   for s in Stock.__members__.items():
#       print (s)

try:
    while True:
        events = sel.select(timeout=select_timeout)
        for key, mask in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            else:
                service_connection(key, mask)
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
finally:
    sel.close()


import curses
# build a lobby

class Lobby():
    def __init__(self, scr, host):
        self.border = scr
        self.border.box()
        self.border.refresh()
        y, x = (i-2 for i in scr.getmaxyx())
        self.scr = self.border.derwin(y, x, 1, 1)
        self.scr.erase()
        self.scr.refresh()

        self.scr.addstr(1, 1, 'Stock Ticker')
        self.scr.addstr(2, 1, f'Connecting...')


        #self.scr.getch()
        self.scr.bkgd(' ', curses.A_DIM)
        self.scr.addstr(3, 1, f'Bro what is up', curses.A_UNDERLINE)
        self.scr.refresh()
        self.scr.getch()

def main(stdscr):
    curses.start_color()
    lobby = Lobby(stdscr, 'localhost')

curses.wrapper(main)

# simple test/exploration of curses
import curses
from curses import wrapper

def main(stdscr):
    # Clear screen
    stdscr.clear()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
    stdscr.addstr(0,0, "RED ALERT!", curses.color_pair(1))

    # getch = poor man's pause at end. Without loop curses exits immediately, as it should
    stdscr.getch()


wrapper(main)

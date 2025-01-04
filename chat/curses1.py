# simple test/exploration of curses
# use of wrapper, example of exception being thrown but terminal remains sane
# and exception is still thrown.
# wrapper does/handles 1. cbreak, 2. noecho, 3. keypad on
import curses

from curses import wrapper

def main(stdscr):
    # Clear screen
    stdscr.clear()

    # This raises ZeroDivisionError when i == 10.
    for i in range(0, 11):
        v = i-10
        stdscr.addstr(i, 0, '10 divided by {} is {}'.format(v, 10/v))

    stdscr.refresh()
    stdscr.getkey()

wrapper(main)

# 2025-01-08
'''
window.getstr() is behaving weirdly. I'd like to just have an experimental
program to try out some basic things.

Ok so you to turn echo() on and its better if you also show the cursor.

NOTE:
- arrow keys don't do anything
- no movement controls like you might see in vi or emacs
- SUPER ULTRA basic entry.  Too bad but that's what you get
- if you go past the end of the window during win.getstr(y, x), it just wraps
    around to the next line which is probably not good
- any area of the screen that is meant to be used for win.getstr() should have
    a curses Window created just for that area. Hitting enter erases things to
    the right within whatever window called getstr() e.g. borders.  
'''

import curses

lst_log = []

def log(msg):
    lst_log.append(str(msg))

def main(stdscr):
    curses.curs_set(0)
    stdscr.box() # add border to whole screen
    curses.echo()
    curses.curs_set(1)
    msg = stdscr.getstr(2, 2)

    key = stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(main)
    for l in lst_log:
        print(l)

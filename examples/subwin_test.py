# 2025-01-08 
# GameBoard (st_gameboard.py) has the concept of Window (which is *not* the
# curses Window). The point was just a simple way to divide up the main window
# into logical sections with some basic management facilities (line drawing,
# checking dimensions, etc).

# Why didn't I just use ncurses Window?? because I thought that might complicate
# redrawing and might be just too much overhead. 

# BUt now I'm wondering if that was a mistake. ncurses subwin() might be a better
# solution, but I'm not exactly sure how they work... 

# so let's test...

# NOTES:
# window.subwin(begin_y, begin_x)   <--- extends to bottom-right of window
# window.subwin(nlines, ncols, begin_y, begin_x)
# -- derwin is same as subwin except begin_y, begin_x are relative to origin of window, rather than relative to the entire screen.
# window.derwin(begin_y, begin_x)
# window.derwin(nlines, ncols, begin_y, begin_x)

# CONCLUSION:
# The GameBoard's Window class is justified.  No gain using subwin/ derwin instead
# - the line drawing facilities (box, border, etc) provided by curses are just not good enought
#    mine are better (auto-chooses joining glyphs sensibly)
# - purpose/usefulness of my Window is gone after initialization.  No need to complicate it further

import curses

lst_log = []

def log(msg):
    lst_log.append(str(msg))

def main(stdscr):
    curses.curs_set(0)
    stdscr.box() # add border to whole screen
    win1 = stdscr.subwin(curses.LINES - 8, curses.COLS - 8, 4, 4)
    win1.box()
    log('hello')

    win2 = win1.subwin(3, 10, 10, 10)
    win2.addstr(1, 1, 'win2')
    win2.box()

    win3 = win1.derwin(3, 10, 10, 10)
    win3.addstr(1, 1, 'win3')
    win3.box()

    key = stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(main)
    for l in lst_log:
        print(l)

# NOTE: does not work on windows!  "_curses not found" or something...
#    ModuleNotFoundError - could check for this

try:
    import curses
except ModuleNotFoundError:
    print ("[curses] library not installed.")
    print ("try > pip install windows-curses")
    exit (1)
import datetime

stdscr = curses.initscr()
curses.noecho()
stdscr.nodelay(1) # set getch() non-blocking

stdscr.addstr(0,0,"Press \"p\" to show count, \"q\" to exit...")
line = 1
try:
    while 1:
        #stdscr.addstr('hi')
        c = stdscr.getch()
        if c == ord('p'):
            stdscr.addstr(line,0,"Some text here")
            line += 1
        elif c == ord('q'): break

        """
        Do more things
        """

finally:
    curses.endwin()

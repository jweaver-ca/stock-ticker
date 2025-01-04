# FROM: https://stackoverflow.com/questions/60468019/python3-curses-with-threading

#!/usr/bin/python3
# date: 2020.02.29 
# platform: raspberry pi 3b+
# python version: 3.5.3
#
# intent: figure out how to get threads to pass messages to the main thread
#         without failure. failure: exiting unexpectedly, throwing exceptions, or corrupting the display.
#
# -v0.0: no thread locking; 5 threads; fails almost instantly.
# -v0.1: thread locking every call to curses methods after threads started; still fails.
# -v0.2: reduced # of threads to 1; takes longer to fail.

import sys,os,time,curses,threading

def threadfunc(ch,blocktime,stdscr):
    while True:
        threadname = 'thread {}'.format(ch)
        with threading.Lock():
            stdscr.addstr(int(curses.LINES/3)-2,int((curses.COLS - len(threadname))/2),threadname)
            stdscr.refresh()
        time.sleep(blocktime)

def main(stdscr):
    if curses.has_colors() == True:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1,curses.COLOR_GREEN,curses.COLOR_BLUE)
        curses.init_pair(2,curses.COLOR_WHITE,curses.COLOR_RED)
        stdscr.bkgd(' ',curses.color_pair(1))

    curses.curs_set(0)      # cursor off.
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)     # receive special messages.

    # instantiate a small window to hold responses to keyboard messages.
    xmsg = 32
    ymsg = 1
    msgwin = curses.newwin(ymsg,xmsg,int(curses.LINES/3),int((curses.COLS - xmsg)/2))
    msgwin.bkgd(' ',curses.color_pair(2))
    stdscr.noutrefresh()
    msgwin.noutrefresh()
    curses.doupdate()

    # make threads, each with slightly different sleep time:
    threadcount = 5
    t = []
    for i in range(threadcount):
        t.append(threading.Thread(target=threadfunc,name='t{}'.format(i),args=(chr(ord('0')+i),0.2+0.02*i,stdscr),daemon=True))
        t[i].start()

    while True:
        with threading.Lock():
            key = stdscr.getch()    # wait for a character; returns an int; does not raise an exception.
        if key == 0x1b:             # escape key exits
            exitmsg = 'exiting...'
            with threading.Lock():
                msgwin.erase()
                msgwin.addstr(0,int((xmsg-len(exitmsg))/2),exitmsg)
            break
        else:
            feedback = 'received {}'.format(chr(key))
            with threading.Lock():
                msgwin.erase()
                msgwin.addstr(0,int((xmsg-len(feedback))/2),feedback)

        with threading.Lock():
            msgwin.refresh()

    del t           # is this the proper way to destroy an object?
    exitmsg = 'press any key to exit'
    stdscr.addstr(int(curses.LINES/2),int((curses.COLS-len(exitmsg))/2),exitmsg)
    stdscr.getkey()

    stdscr.keypad(False)
    curses.nocbreak()
    curses.echo()
    curses.endwin()

if __name__ == '__main__':
    # Must happen BEFORE calling the wrapper, else escape key has a 1 second delay after pressing:
    os.environ.setdefault('ESCDELAY','100') # in mS; default: 1000
    curses.wrapper(main)

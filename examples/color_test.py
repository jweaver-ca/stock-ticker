import curses

def main(stdscr):
    curses.start_color()
    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_WHITE)
        stdscr.addstr(2, 2, 'Hello red', curses.color_pair(1))
        stdscr.addstr(4, 2, 'Hello red w white bg', curses.color_pair(2))
        stdscr.addstr(6, 2, 'Hello red REV', curses.color_pair(1) | curses.A_REVERSE)
        stdscr.addstr(8, 2, 'Hello red w white bg REV', curses.color_pair(2) | curses.A_REVERSE)

        stdscr.refresh()  # stdscr refresh 1

        #subwin = stdscr.derwin(5, 25, 10, 2)
        subwin = curses.newwin(5, 25, 10, 2)

        subwin.bkgd(' ', curses.color_pair(1))
        subwin.addstr(1,1, 'whatever')
        subwin.box()
        #stdscr.refresh()
    else:
        stdscr.addstr(2, 2, 'no color', curses.COLOR_RED)

    # NOTE: if you use stdscr for getch and you don't call stdscr.refresh() after its
    #       modifications, stdscr will get a refresh called on it as soon as getch() is
    #       called.  This could unexpectedly hide the contents of subwin
    #stdscr.getch()
    subwin.getch()
    
    

curses.wrapper(main)

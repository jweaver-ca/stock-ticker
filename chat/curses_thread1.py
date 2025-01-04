# most basic curses and OOP threading
# NOTES:
# - if in your program the main thread polls for keyboard (getch()) input, threading
#   the keyboard in this way may not be required, but this is a good illustration
import threading
try:
    from curses import wrapper
except ModuleNotFoundError:
    # once installed on system, this all goes away
    print ("[curses] library not installed.")
    print ("try > pip install windows-curses")
    exit (1)

keypresscount = 0

class KeyboardThread(threading.Thread):
    def __init__(self, name, scr):
        super().__init__(name=name)
        self.scr = scr

    def run(self):
        while True:
            val = self.scr.getch() # blocking (since curses.nodelay() not called)
            if val == ord('q'):
                break # quit on 'q'
            global keypresscount # global required else UnboundLocalError thrown
            keypresscount += 1
            self.scr.addstr(str(val)) # just print the # to the screen
            self.scr.refresh()
            
def main(stdscr):
    kt = KeyboardThread('keyboard-thread', stdscr)
    stdscr.clear()
    stdscr.addstr("Keypress values echoed to the screen. 'q' to exit\n")
    stdscr.refresh() # refresh required every time there is a change if you want to actually see it!
    kt.start() # non-blocking of course
    kt.join() # required in this case to prevent main thread from exiting (and so ruining terminal protections given by 'wrapper()')

wrapper(main)
# curses is gone, message goes to regular terminal
print (f'Total keypresses: {keypresscount}')

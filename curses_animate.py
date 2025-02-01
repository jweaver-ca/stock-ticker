'''
Enable simple animations on the gameboard.

An AnimationThread (AT) will be created and started when the gameboard
is created.  It will have a repeating tick. Every tick it will check
if there are animations to draw in the queue, enact them, and remove
them from the queue.

All animations will basically consist of applying curses attributes to
a portion of the screen e.g. flashing colors, or reverse video, etc.
'''
import curses
import threading
import time

class Animation():
    ''' Basically just holds the curses.chgat() info needed to make the update
    and the AnimationThread tick count to wait before applying
    '''
    def __init__(self, y, x, width, attr, ticks):
        self.y      = y
        self.x      = x
        self.width  = width
        self.attr   = attr
        self.ticks  = ticks

class AnimationThread(threading.Thread):
    def __init__(self, curses_scr, drawlock):
        ''' 
        curses_scr: curses window/screen to apply the animations to
        drawlock: draw operations in curses should be thread-locked. 
        '''
        super().__init__()
        self.daemon = True
        self.interval_sec = 0.2
        self.running = True
        self.scr = curses_scr
        self.drawlock = drawlock
        self.animations = dict() # key: key for deletion, value: list of animations

    def add_flash(self, key, y, x, width, attr_on, attr_off=curses.A_NORMAL, cycles=2, rate=1):
        if key in self.animations:
            raise ValueError(f"key [{key}] already exists")
        self.animations[key] = []
        i_tick = rate
        attr = attr_on
        for _ in range(cycles):
            self.animations[key].append(Animation(y, x, width, attr_on, i_tick))
            self.animations[key].append(Animation(y, x, width, attr_off, i_tick+rate))
            i_tick += rate * 2
            
    def run(self):
        while self.running:
            time.sleep(self.interval_sec)
            if self.running: # skip action if game has ended
                animations_to_execute = []
                keys_to_delete = []
                for key, lst_a in self.animations.items():
                    animations_left = False
                    # execute animation when ticks is 0, delete the whole key once all are executed
                    for a in lst_a:
                        a.ticks -= 1
                        if a.ticks == 0:
                            animations_to_execute.append(a)
                        elif a.ticks > 0:
                            animations_left = True
                    if not animations_left:
                        keys_to_delete.append(key)
                        #del self.animations[key]
                if animations_to_execute:
                    with self.drawlock:
                        for a in animations_to_execute:
                            self.scr.chgat(a.y, a.x, a.width, a.attr)
                        self.scr.refresh()
                for k in keys_to_delete:
                    del self.animations[k]
                            


# ScrollArea should be implemented as a curses window using ths .scroll instead
# a half-assed implementation as it is now
# biggest reason: color will scroll, we hope?  that's what this test is about

import curses
import textwrap
import threading


# ScrollArea class using a curses windows instead

# exact copy from gameboard
class Window(object):
    '''
    A rectangular section on the gameboard that represents one part of the whole display
    e.g. the current prices and holdings of the stocks would be in one window.  Chat
    messages between players in another, etc

    This idea is to aid in changing the layout of the GameBoard by allowing the Window's
    to manage their own internal structure, placing and updating of fields, etc.
    
    Window objects will be passed by the gameboard into its functions for adding text, fields,
    etc. onto the board to allow placement relative to the window's location, rather than the
    whole board.  Window objects will not serve much other purpose.

    The dimensions described by uly, ulx, h, w are the *inner* part of the window but there should
    be a 1-char-wide border left around it for the GameBoard to draw border lines between adjecent
    Window's.  Since the border chars can be shared by other (up to 4 total) Window's, drawing lines
    *within* windows must be handled by the GameBoard so the correct connecting glyphs can be used
    when required. This is done by passing dict_border_cells to line drawing facilities before the
    final drawing is done by the GameBoard

    Window objects are not related to the concept of curses windows objects, the GameBoard will
    still exist as a single curses screen.

    The intention is that during the init/design phase most operations requiring a coord within the
    window will be relative to the Window's uly/ulx values, not the GameBoard's (except the
    constructor!)
    '''

    def __init__(self, uly, ulx, height, width):
        '''
        uly/ulx: upper left curses coord of the window within the GameBoard. These should
            be constant once initialized.
        '''
        self.uly = uly
        self.ulx = ulx
        self.height = height
        self.width = width

    def TY(self): # top Y
        return self.uly

    def BY(self): # bottom Y
        return self.uly + self.height - 1

    def LX(self): # left X
        return self.ulx

    def RX(self): # right X
        return self.ulx + self.width - 1

    def UL(self): # upper left
        return YXCoord((self.uly, self.ulx))

    def UR(self): # upper right
        return YXCoord((self.uly, self.RX()))

    def LL(self): # lower left
        return YXCoord((self.BY(), self.ulx))

    def LR(self): # lower right
        return YXCoord((self.BY(), self.RX()))

    def draw_hline(self, dict_border_cells, yfromborder, from_side_borders=None):
        '''
        Draw a horizontal line in the given window (win)
        Must be called during init phase before GameBoard calls draw_border
        NOTE: Lines drawn in windows can connect to the outer border which is conceptually
            outside the window's area so the usual Window coordinate system isn't used.
        yfromborder: (1+) lines from top of window. 1 is directly below the top border
            negative means up from bottom border of window
        from_side_borders: optional 2-tuple (left,right) for spaces from the left/right edge
            (default (0,0))
        '''
        (uly, ulx, h, w) = self.dimensions()
        # ensure line is within window
        if yfromborder == 0 or yfromborder > h or yfromborder < -h:
            raise ValueError(f"yfromborder [{yfromborder}] outside the window boundary")
        if from_side_borders is None:
            from_side_borders = (0,0)
        if any([x<0 for x in from_side_borders]):
            raise ValueError(f"from_side_borders [{from_side_borders}] can't have values less than zero")
        if yfromborder >= 1:
            y = uly-1 + yfromborder
        else:
            y = uly+h + yfromborder
        base_brdr_val = GameBoard.BRDR_LEFT | GameBoard.BRDR_RIGHT 
        for x in range(ulx-1+from_side_borders[0], ulx+w+1-from_side_borders[1]):
            key = (y, x)
            brdr_val = base_brdr_val
            if x == ulx-1:
                brdr_val &= ~GameBoard.BRDR_LEFT
            elif x == ulx+w:
                brdr_val &= ~GameBoard.BRDR_RIGHT
            GameBoard._border_cell_val(key, brdr_val, dict_border_cells)
            #print (f"{key} {brdr_val} {dict_border_cells[key]} {self.LKU_BORDER[dict_border_cells[key]]}")
            #print (f"{key} {brdr_val} {dict_border_cells[key]}")

    def draw_vline(self, dict_border_cells, xfromborder, from_tb_borders=(0,0)):
        '''
        Draw a vertical line in the given window (win)
        Must be called during init phase before GameBoard calls draw_border
        NOTE: Lines drawn in windows can connect to the outer border which is conceptually
            outside the window's area
        xfromborder: (1+) lines from left of window. 1 is directly to right of the left border
            negative means left from right border of window
        from_tp_borders: optional 2-tuple (top,bottom) for spaces from the top/bottom edge
            (default (0,0))
        '''
        (uly, ulx, h, w) = self.dimensions()
        # ensure line is within window
        if xfromborder == 0 or xfromborder > w or xfromborder < -w:
            raise ValueError(f"xfromborder [{xfromborder}] outside the window boundary")
        if any([x<0 for x in from_tb_borders]):
            raise ValueError(f"from_tb_borders [{from_tb_borders}] can't have values less than zero")
        if xfromborder >= 1:
            x = ulx-1 + xfromborder
        else:
            x = ulx+w + xfromborder
        base_brdr_val = GameBoard.BRDR_UP | GameBoard.BRDR_DOWN
        for y in range(uly-1+from_tb_borders[0], uly+h+1-from_tb_borders[1]):
            key = (y, x)
            brdr_val = base_brdr_val
            if y == uly-1:
                brdr_val &= ~GameBoard.BRDR_UP  # remove the top part
            elif y == uly+h:
                brdr_val &= ~GameBoard.BRDR_DOWN
            GameBoard._border_cell_val(key, brdr_val, dict_border_cells)

    def dimensions(self):
        '''
        return tuple uly, ulx, height, width
        '''
        return (self.uly, self.ulx, self.height, self.width)

class ScrollArea(Window):
    '''
    Simple upwards scroll area (starts at bottom)
    Lines are split according to width of the given window
    '''
    # I dont like giving win and cwin but
    # win: is for initial drawing following the paradigm of other gameboard parts
    # parent_cwin: is required to actually draw and call derwin, whereas Window types aren't
    #    conclusion: need both for now, unless we rethink everything
    def __init__(self, parent_cwin, win, drawlock, offset=None):
        '''
        window: Window where this will go
        offset: tuple (left,up,right,down), if not given, all zeros (whole window)
        drawlock: drawing lock provided by GameBoard to synchronize drawing
        '''
        if offset is None:
            offset = (0, 0, 0, 0)
        # make sure offset is legal for window size
        if any([x<0 for x in offset]):
            raise ValueError(f"bad offset [{offset}]")
        thisheight = win.uly - (offset[1]+offset[3])
        thiswidth = win.ulx - (offset[0]+offset[2])
        self.width = thiswidth
        self.BY = thisheight-1
        thisy, thisx = win.uly + offset[1], win.ulx + offset[0]
        if (thiswidth < 0) or (thisheight < 0):
            raise ValueError(f"offset is too large for window [{offset}]")
        self.drawlock = drawlock
        #self.window = Window(window.uly+offset[1], window.ulx+offset[0], thisheight, thiswidth)
        self.cwin = parent_cwin.subwin(thisheight, thiswidth, thisy, thisx)
        self.maxy, self.maxx = self.cwin.getmaxyx()

    def add_message(self, str_message, attr=curses.A_NORMAL):
        #TODO: find a better/efficient way to clear lines besides formatting the string to fill with spaces on the right
        #      mostly its just confusing why this formatting is done...
        lst_msg = textwrap.wrap(str_message,width=self.width)
        with self.drawlock:
            self.cwin.scroll()
            for i, msgpart in enumerate(lst_msg):
                y = self.BY -len(lst_msg) + i
                self.cwin.addstr(y, 0, lst_msg[i], attr)
            self.cwin.refresh()
            
def main(stdscr):
    lock = threading.Lock()
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    stdscr.addstr(2, 2, 'HERE IS A MESSAGE', curses.color_pair(1))
    stdscr.refresh()
    dict_border_cells = dict() # key = tuple (y,x), value = 

    scrollwin = Window(10, 30, 2, 20)
    sa_test1 = ScrollArea(stdscr, scrollwin, lock)
    sa_test1.cwin.box()
    sa_test1.cwin.scrollok(True)
    #sa_test1.cwin.addstr(0, 0, 'hello dude')
    #self, nlines, ncols, y, x, drawlock, offset=None):
    for i in range(16):
        print (i)
        attr = curses.A_NORMAL
        if i == 9:
            attr = curses.color_pair(1)
        sa_test1.add_message(f'{i:02} here is', attr)
    sa_test1.cwin.refresh()
    sa_test1.cwin.getch()

if __name__ == '__main__':
    curses.wrapper(main)

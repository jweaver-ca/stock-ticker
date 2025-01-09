import curses
import curses.panel
import textwrap

# for debugging only. remove when done with it
lst_log = []
def log(msg):
    lst_log.append(str(msg))

class GameBoard(object):
    '''
    List of stock names provided for init.  GameBoard will only deal stocks via the integer value of the
    index of each stock within that list.  The expectation is that the names will never vary but I'll 
    try to build in flexibility as to the number of stocks and the layout of the game board to automatically
    adjust as needed.

    GameBoard will be dumb to curses for the most part (hopefully completely).  Only the main function
    will be required to call curses functions in order to test. The goal is to otherwise not require
    access to the 'curses' object in the namespace

    ┌─┬─┐
    │ │ │
    ├─┼─┤
    │ │ │
    └─┴─┘
    '''
    # NOTE: would be maybe good to have option of providing screen or have GameBoard create it?
    # NOTE: a smart programmer would make GameBoard a (abstract) superclass with generic windowing,
    #       bordering, updating facilities and then make STBoard a sub-class with specific implementation
    #       for a stock-ticker game.  I've tried to adopt that spirit so it *could* be separated in the
    #       future if I'm not too lazy...
    # self.scr = the screen its on

    # flags used for drawing borders (see: dict_border_cells)
    BRDR_LEFT = 1
    BRDR_UP = 2
    BRDR_RIGHT = 4
    BRDR_DOWN = 8

    # characters for drawing borders
    BC_HLINE    = '─'
    BC_VLINE    = '│'
    BC_VLEFT    = '┤'
    BC_VRIGHT   = '├'
    BC_HUP      = '┴'
    BC_HDOWN    = '┬'
    BC_URCORNER = '┐'
    BC_ULCORNER = '┌'
    BC_LRCORNER = '┘'
    BC_LLCORNER = '└'
    BC_ALL      = '┼'

    # maps OR'd values of BRDR_* to the glyphs in BC_*
    # NOTE: the missing ones are lone values (1,2,4,8) which never happen
    LKU_BORDER = {
        0: ' ',
        3: BC_LRCORNER,
        5: BC_HLINE,
        6: BC_LLCORNER,
        7: BC_HUP,
        9: BC_URCORNER,
        10: BC_VLINE,
        11: BC_VLEFT,
        12: BC_ULCORNER,
        13: BC_HDOWN,
        14: BC_VRIGHT,
        15: BC_ALL      
    }


    def __init__(self, stdscr, lst_stock_names):
        self.scr = stdscr
        self.max_stock_price = 999 # no more than 3 digits!
        self.min_stock_price = 0
        self.scr.addstr("Hello dude")
        self.stock_names = lst_stock_names

        self.fields = dict() # Field objects
        self.coords = dict() # named coordinate locations

        # lets try a virtual window or two...
        #self.win_market = (1, 1, 11, 34) # uly, ulx, h, w
        (scry, scrx) = stdscr.getmaxyx()
        self.win_main = Window(1, 1, scry-2, scrx-2)

        # Top section
        self.win_top = Window(self.win_main.TY(), self.win_main.LX(), 3, self.win_main.width)
        str_title = '-=  S T O C K   T I C K E R  =-'
        self.add_text(self.win_top, 0, 0, str_title, self.win_top.width, justify='^')
        str_status = 'Status: '
        str_players = 'Players: '
        self.add_text(self.win_top, 1, 1, str_status)
        self._add_field("status", self.win_top, 1, len(str_status) + 1, self.win_top.width - len(str_status) -1, initval='< disconnected >', justify='<')
        self.add_text(self.win_top, 2, 1, str_players)
        self._add_field("players", self.win_top, 2, len(str_players) + 1, self.win_top.width - len(str_status) -1, initval='???', justify='<')

        # Market section
        self.win_market = self.add_window_below(self.win_top, 11, 34)

        # buysell
        self.win_buysell = self.add_window_right(self.win_market, None, 24)

        # mkt_act (market activity)
        self.win_mkt_act = self.add_window_right(self.win_buysell, None, 22)

        # bottom of screen
        # hotkey
        self.win_hotkey = Window(self.win_main.BY(), self.win_main.LX(), 1, self.win_main.width) 
        self.add_text(self.win_hotkey, 0, 1, '[M]essage  [R]equest Pause  [Q]uit')

        # chatmsg - entry window for typing chat message to other players
        self.win_chatmsg = Window(self.win_hotkey.TY()-2, self.win_main.LX(), 1, self.win_main.width) 
        self.add_text(self.win_chatmsg, 0, 1, '>')
        self._add_coord('input-chat', self.win_chatmsg, 0, 3)
        width_chatmsg_in = self.win_chatmsg.RX() - self.get_coord('input-chat').X
        self.cwin_chatmsg_in = self.scr.subwin(1, width_chatmsg_in, *self.get_coord('input-chat').val())

        # sysmsg - system/game/chat messages
        self.win_sysmsg = Window(self.win_market.BY()+2, self.win_main.LX(), self.win_chatmsg.TY()-self.win_market.BY()-1, self.win_main.width) 


        dict_border_cells = dict() # key = tuple (y,x), value = 
        GameBoard.apply_border(self.win_main, dict_border_cells)
        GameBoard.apply_border(self.win_top, dict_border_cells)
        GameBoard.apply_border(self.win_market, dict_border_cells)
        GameBoard.apply_border(self.win_buysell, dict_border_cells)
        GameBoard.apply_border(self.win_mkt_act, dict_border_cells)
        GameBoard.apply_border(self.win_hotkey, dict_border_cells)
        GameBoard.apply_border(self.win_sysmsg, dict_border_cells)
        GameBoard.apply_border(self.win_chatmsg, dict_border_cells)

        self._init_draw_market(dict_border_cells)
        self._init_draw_buysell(dict_border_cells)
        self._init_draw_mkt_act(dict_border_cells)

        #NOTE: I don't like the heading, and it takes up too much room
        #self.win_sysmsg.draw_hline(dict_border_cells, 2)
        #self.add_text(self.win_sysmsg, 0, 1, 'SYSTEM MESSAGES')

        # last thing after all windows have drawn their lines, borders, etc
        self.draw_border(dict_border_cells)


    def add_window_right(self, ref_win, height=None, width=None):
        '''
        Convenience method for adding a new Window located relative to an existing
        Window rather than specify the dimensions.  This window will be placed
        directly to the right of ref_win aligned along the top edge. If height or
        width are None or omitted, copy them from ref_win for this new window
        '''
        if height is None:
            height = ref_win.height
        if width is None:
            width = ref_win.width
        return Window(ref_win.TY(), ref_win.RX()+2, height, width)

    def add_window_below(self, ref_win, height, width):
        '''
        Convenience method for adding a new Window located relative to an existing
        Window rather than specify the dimensions.  This window will be placed
        directly below ref_win aligned along the left edge. If height or width are
        None or omitted, copy them from ref_win for this new window
        '''
        if height is None:
            height = ref_win.height
        if width is None:
            width = ref_win.width
        return Window(ref_win.BY()+2, ref_win.LX(), height, width)

    def show_modal(self, wdialog):
        # NOTE: this can probably be removed, but I'm not sure yet
        pass

    def update_stock_price(self, i_stock, new_price, bln_pays_div):
        if new_price > self.max_stock_price:
            raise ValueError(f"[{new_price}] too high to display")
        elif new_price < self.min_stock_price:
            raise ValueError(f"[{new_price}] too low")
        char_pays_div = "✓" if bln_pays_div else " "
        self.update_field(f'stockprice-{i_stock}', new_price)
        self.update_field(f'stockdiv-{i_stock}', char_pays_div)

    def apply_border(win, dict_border_cells):
        '''
        Modifies dict_border_cells adding the border parts that will be required
        for the given window. (DOES NOT DRAW)
        win: the tuple (uly, ulx, h, w) defining the *inside* of the window. The border will
            go *outside* of that area by 1 char
        '''
        # do the 4 corners
        GameBoard._border_cell_val((win.uly-1, win.ulx-1), GameBoard.BRDR_DOWN|GameBoard.BRDR_RIGHT, dict_border_cells)
        GameBoard._border_cell_val((win.uly+win.height, win.ulx-1), GameBoard.BRDR_UP|GameBoard.BRDR_RIGHT, dict_border_cells)
        GameBoard._border_cell_val((win.uly-1, win.ulx+win.width), GameBoard.BRDR_DOWN|GameBoard.BRDR_LEFT, dict_border_cells)
        GameBoard._border_cell_val((win.uly+win.height, win.ulx+win.width), GameBoard.BRDR_UP|GameBoard.BRDR_LEFT, dict_border_cells)
        # do the right/left edges
        for y in range(win.uly, win.uly+win.height):
            lkey = (y, win.ulx-1)
            rkey = (y, win.ulx+win.width)
            GameBoard._border_cell_val(lkey, GameBoard.BRDR_DOWN|GameBoard.BRDR_UP, dict_border_cells)
            GameBoard._border_cell_val(rkey, GameBoard.BRDR_DOWN|GameBoard.BRDR_UP, dict_border_cells)
        # do the top/bottom edges
        for x in range(win.ulx, win.ulx+win.width):
            hkey = (win.uly-1, x)
            lkey = (win.uly+win.height, x)
            GameBoard._border_cell_val(hkey, GameBoard.BRDR_LEFT|GameBoard.BRDR_RIGHT, dict_border_cells)
            GameBoard._border_cell_val(lkey, GameBoard.BRDR_LEFT|GameBoard.BRDR_RIGHT, dict_border_cells)
    
    def draw_border(self, dict_border_cells):
        maxkey = tuple(x-1 for x in self.scr.getmaxyx())
        for key, val in dict_border_cells.items():
            if val in self.LKU_BORDER:
                brdr_char = self.LKU_BORDER[val]
            else:
                brdr_char = '?'
            # handling the error thrown when addch (which causes cursor to move into illegal area) writes to bottom-right of window
            if key == maxkey:
                self.scr.insstr(*key, brdr_char)
            else:
                self.scr.addch(*key, brdr_char)
        
    def add_text(self, win, y, x, text, width=None, justify=None):
        '''
        Add text to GameBoard inside the given Window
        win: Window to add text to
        y: if 0+, offset from top of window.  If -1 or less, offset from bottom of window, 
            -1 indicating the bottom-most line
        x: if 0+, offset from left of window.  If -1 or less, offset from right of window,
            -1 indicating the right-most column. text *ends* at this point
        width and justify must be both be given or neither.  justify is one of '<', '^', '>'
            and width is the length of the field to justify the the within.
        '''
        if width is not None:
            if justify not in ['<', '^', '>']:
                raise ValueError(f"Invalid value for justify [{justify}]")
            str_text = f"{text:{justify}{width}s}"
        else:
            if justify is not None:
                raise ValueError(f"Must provide width along with justify")
            str_text = str(text)
            
        (thisy, thisx) = (y, x)
        if y < 0:
            thisy = win.height - (abs(y)-1) - 1
        if x < 0:
            thisx = win.width - (abs(x)-1) - len(str_text)
        self.scr.addstr(win.uly+thisy, win.ulx+thisx, str_text)

    def _border_cell_val(key, value, dict_border_cells):
        if not key in dict_border_cells:
            dict_border_cells[key] = 0
        dict_border_cells[key] |= value

    def _init_draw_market(self, dict_border_cells):
        (uly, ulx, h, w) = self.win_market.dimensions()
        yoff = 2 # y from top of window to start
        xoff = 3
        max_name_len = max([len(x) for x in self.stock_names])
        len_stockprice = 3
        xprice = xoff + max_name_len + 2 # 2 right of longest stock name
        xdiv = xprice + len_stockprice + 1
        xminus = xdiv + 3
        xowned = xminus + 2
        lenowned = 6 # num of digits allowed for owned
        xplus = xowned + lenowned + 2
        self.ul_stockprice = (yoff, xprice) # store upper left of stock prices
        for i, stockname in enumerate(self.stock_names):
            self.add_text(self.win_market, yoff+i, xoff, stockname)
            self._add_field(f'stockprice-{i}', self.win_market, yoff+i, xprice, len_stockprice, '>', initval=0)
            self._add_field(f'stockdiv-{i}', self.win_market, yoff+i, xdiv, 1)
            # TODO: these +/- will have to be implemented as controls soon...
            self.add_text(self.win_market, yoff+i, xminus, '-')
            self.add_text(self.win_market, yoff+i, xplus, '+')
            self._add_field(f'stockowned-{i}', self.win_market, yoff+i, xowned, lenowned, initval=0, justify='>')
        #self._draw_hline(dict_border_cells, self.win_market, 1)
        self.win_market.draw_hline(dict_border_cells, 2)
        self.win_market.draw_hline(dict_border_cells, 9)
        str_market1 = 'MARKET VAL/DIV       OWNED'
        str_cash = 'Cash:      $'
        str_net_worth = 'Net Worth: $'
        self.add_text(self.win_market, 0, 4, str_market1)
        ycash = yoff+len(self.stock_names)+1
        self.add_text(self.win_market, ycash, 1, str_cash)
        self.add_text(self.win_market, ycash+1, 1, str_net_worth)
        self._add_field('cash', self.win_market, ycash, 1+len(str_cash), 7, initval=0, justify='>')
        self._add_field('networth', self.win_market, ycash+1, 1+len(str_net_worth), 7, initval=0, justify='>')

    def _init_draw_buysell(self, dict_border_cells):
        win = self.win_buysell
        (uly, ulx, h, w) = win.dimensions()
        win.draw_hline(dict_border_cells, 2)
        midx = int(win.width/2)
        win.draw_vline(dict_border_cells, midx)
        str_pending = 'PENDING'
        str_block = '$/BLOCK'
        str_blocksz = 'BLOCK SZ'
        self.add_text(win, 0, 0, str_pending, midx, '^')
        self.add_text(win, 0, midx, str_block, midx, '^')
        width_pending = midx - 3 # (-1 because a line is there, and -1 for a space on each side)
        width_blockprice = width_pending # blockprice should always be wider so this is safe... right?
        yoff = 2
        for i, stockname in enumerate(self.stock_names):
            self._add_field(f'pending-{i}', self.win_buysell, yoff+i, 1, width_pending, '>', initval=0)
            self._add_field(f'blockprice-{i}', self.win_buysell, yoff+i, midx + 2, width_blockprice, '>', initval=0)
        ybot = yoff + len(self.stock_names) + 1 # top row of bottom section of window
        self.add_text(win, ybot, 1, '$') # label for dollar amount under pending
        self._add_field('pending-$', self.win_buysell, ybot, 2, width_pending-1, '>', initval=0)
        self.add_text(win, ybot, midx, str_blocksz, midx, '^')
        self.add_text(win, ybot+1, midx+1, '[')
        self.add_text(win, ybot+1, win.width-2, ']')
        self._add_field('blocksz', self.win_buysell, ybot+1, midx+4, 5, '>', initval=500)
        
    def _init_draw_mkt_act(self, dict_border_cells):
        win = self.win_mkt_act
        (uly, ulx, h, w) = win.dimensions()
        win.draw_hline(dict_border_cells, 2)
        str_head = 'MARKET ACTIVITY'
        str_next_action = 'NEXT ACTION IN:'
        if len(str_head) > win.width:
            raise ValueError(f"Title [{str_head}] too long for window")
        self.add_text(win, 0, 0, str_head, win.width, justify='^')
        xlowline = -3
        win.draw_hline(dict_border_cells, xlowline)
        self.add_text(win, -2, 0, str_next_action, win.width, justify='^')
        # TODO: ScrollAreas, like labels maybe should be accessible by a name??
        self.sa_mkt_act = ScrollArea(self.scr, self.win_mkt_act, offset=(1,2,1,3))
        self._add_field('next-action', win, win.height-1, 1, win.width-2, justify='^', initval="00:00.0")

        
    def _draw_hline(self, dict_border_cells, win, yfromborder, from_side_borders=None):
        # NOTE: not used and probably can be removed. Use Window.draw_hline
        '''
        Draw a horizontal line in the given window (win)
        Must be called during init phase before GameBoard calls draw_border
        NOTE: Lines drawn in windows can connect to the outer border which is conceptually
            outside the window's area
        yfromborder: (1+) lines from top of window. 1 is directly below the top border
            negative means up from bottom border of window
        from_side_borders: optional 2-tuple (left,right) for spaces from the left/right edge
            (default (0,0))
        '''
        (uly, ulx, h, w) = win.dimensions()
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
        base_brdr_val = self.BRDR_LEFT | self.BRDR_RIGHT 
        for x in range(ulx-1+from_side_borders[0], ulx+w+1-from_side_borders[1]):
            key = (y, x)
            brdr_val = base_brdr_val
            if x == ulx-1:
                brdr_val &= ~self.BRDR_LEFT
            elif x == ulx+w:
                brdr_val &= ~self.BRDR_RIGHT
            GameBoard._border_cell_val(key, brdr_val, dict_border_cells)
            #print (f"{key} {brdr_val} {dict_border_cells[key]} {self.LKU_BORDER[dict_border_cells[key]]}")
            #print (f"{key} {brdr_val} {dict_border_cells[key]}")

    def _draw_vline(self, dict_border_cells, win, xfromborder, from_tb_borders=(0,0)):
        # NOTE: not used and probably can be removed. Use Window.draw_vline
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
        (uly, ulx, h, w) = win.dimensions()
        # ensure line is within window
        if xfromborder == 0 or xfromborder > w or xfromborder < -w:
            raise ValueError(f"xfromborder [{xfromborder}] outside the window boundary")
        if any([x<0 for x in from_tb_borders]):
            raise ValueError(f"from_tb_borders [{from_tb_borders}] can't have values less than zero")
        if xfromborder >= 1:
            x = ulx-1 + xfromborder
        else:
            x = ulx+w + xfromborder
        base_brdr_val = self.BRDR_UP | self.BRDR_DOWN
        for y in range(uly-1+from_tb_borders[0], uly+h+1-from_tb_borders[1]):
            key = (y, x)
            brdr_val = base_brdr_val
            if y == uly-1:
                brdr_val &= ~self.BRDR_UP  # remove the top part
            elif y == uly+h:
                brdr_val &= ~self.BRDR_DOWN
            GameBoard._border_cell_val(key, brdr_val, dict_border_cells)

    def _add_field(self, name, win, y, x, length, justify='<', initval=None):
        # TODO: y/x should allow negative and be 1-based. not 0
        if name in self.fields:
            raise ValueError(f"Field with name [{name}] already exists")
        self.fields[name] = Field(win, y, x, length, justify)
        if initval is not None:
            self.update_field(name, initval)

    def _add_coord(self, name, win, y, x):
        '''
        store a named coordinate (YXCoord) on the board relative to the given
        window.
        y, x: 0-based offset from upper-left corner of window (i.e. 0, 0 is
            the top-left corner)
        if y and/or x are negative, it's 1-based from the opposite side i.e
            (-1, -1) is the bottom-right
        '''
        if name in self.coords:
            raise ValueError(f"Coord with name [{name}] already exists")
        # get 0-based offset from windows edges
        thisy = win.TY()+y if y>=0 else win.BY() - abs(y) + 1
        thisx = win.LX()+x if x>=0 else win.RX() - abs(x) + 1
        self.coords[name] = YXCoord(thisy, thisx)

    def get_coord(self, name):
        return self.coords[name]

    def update_field(self, name, newval):
        self.fields[name].update(self.scr, newval)

    def input_chat_message(self):
        # NOTE: getstr really has to go in a curses window proper, else the entry
        #   ruins stuff to the right that's in the same window
        curses.echo()
        curses.curs_set(1)
        msg = self.cwin_chatmsg_in.getstr()
        self.cwin_chatmsg_in.erase()
        curses.curs_set(0)
        curses.noecho()
        # NOTE: refresh required to clear out the contents and hide the cursor, etc
        self.cwin_chatmsg_in.refresh()
        # TODO: actually send the dang message

    # --END class GameBoard

class YXCoord(object):
    '''
    Just a Y,X coordinate with some basic operations.
        y_or_yx: if 2-tuple, applies (y,x) error if x provided.
            if int, store as y, x is required
            if YXCoord obj, makes a new object with same coords
        x (int): only given if y is int - not tuple
    '''
    def __init__(self, y_or_yx, x=None):
        if type(y_or_yx) == int:
            self.Y = y_or_yx
            self.X = x
        elif type(y_or_yx) == YXCoord:
            self.Y = y_or_yx.Y
            self.X = y_or_yx.X
        else:
            self.Y = y_or_yx[0]
            self.X = y_or_yx[1]

    def offset(self, y, x):
        '''
        Return a new YXCoord object offset from this one by (y, x)
        '''
        return YXCoord(self.Y+y, self.X + x)

    def val(self):
        '''
        Return a 2-tuple (y,x) of this object's coords
        '''
        return (self.Y, self.X)

    def range(self, rlen=None, last=None, vert=False):
        '''
        Iterable that starts at this obejct coords, and returns one YXCoord at a time adjacent
            to the last one in a line defined by rlen, last and vert
        rlen: length of range. zero means no iteration at all will take. If rlen is
            negative, x value will decrease with each iteration
        last: last value of x (or y if vert is True) to be returned. If last
            is given, there will always be at least one iteration. If last is less than
            X (or Y) in this object, X/Y value will descrease with each iteration
        vert: if True, iterates vertically instead of horizontally
        '''
        if sum([val is None for val in [rlen, last]]) != 1:
            raise ValueError("Exactly 1 of the optional traversal args must be given")
        # figure out the count
        initval = self.Y if vert else self.X
        if rlen is not None:
            if rlen == 0:
                return None
            last_plus1 = initval + rlen
        else:
            # last was given instead
            last_plus1 = last + (1 if last >= initval else -1)
        if vert:
            offset = (-1, 0) if last_plus1 < self.Y else (1, 0)
        else:
            offset = (0, -1) if last_plus1 < self.X else (0, 1)
        count = abs(last_plus1 - initval) 
        lastval = YXCoord(self.Y, self.X)
        for i in range(count):
            yield lastval
            lastval = lastval.offset(*offset)

    def __repr__(self):
        return f"[{self.Y},{self.X}]"

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

class Field(object):
    '''
    An updateable portion of the GameBoard.  Fields are created using offsets from the window that
    contains them, but internally will remember their coords within the GameBoard's main window.
    Fields will be managed by the GameBoard, not the Window
    - length: number of chars
    - justify: '<', '>', '^' (left, right, center as in f-strings)
    '''
    def __init__(self, win, offsety, offsetx, length, justify='<'):
        self.win = win
        self.y = win.uly+offsety
        self.x = win.ulx+offsetx
        self.length = length
        if justify not in ('<', '>', '^'):
            raise ValueError(f"Bad value for just justify: [{justify}]")
        self.justify = justify

    def update(self, scr, newval):
        str_newval = str(newval)
        if len(str_newval) > self.length:
            raise ValueError(f"newval [{newval}] too long for this Field")
        str_fullval = f"{str_newval:{self.justify}{self.length}s}"
        scr.addstr(self.y, self.x, str_fullval)

        

class ScrollArea(object):
    '''
    Simple upwards scroll area (starts at bottom)
    Lines are split according to width of the given window
    '''
    def __init__(self, scr, window, offset=None):
        '''
        scr: curses window (from GameBoard)
        window: tuple (uly, ulx, h, w) where this will go
        offset: tuple (left,up,right,down), if not given, all zeros (whole window)
        '''
        if offset is None:
            offset = (0, 0, 0, 0)
        # make sure offset is legal for window size
        if any([x<0 for x in offset]):
            raise ValueError(f"bad offset [{offset}]")
        thiswidth = window.width - (offset[0]+offset[2])
        thisheight = window.height - (offset[1]+offset[3])
        if (thiswidth < 0) or (thisheight < 0):
            raise ValueError(f"offset is too large for window [{offset}]")
        self.messages = []
        self.scr = scr
        #self.window = window
        self.window = Window(window.uly+offset[1], window.ulx+offset[0], thisheight, thiswidth)
        #self.height = self.window.height
        #self.width = self.window.width
        self.firsty = self.window.uly + self.window.height # bottom line (first)
        print (self.window.dimensions())


    def add_message(self, str_message):
        lst_msg = [ f"{x:<{self.window.width}}" for x in textwrap.wrap(str_message,width=self.window.width)][::-1]
        self.messages = lst_msg + self.messages[:self.window.height-len(lst_msg)]
        #for i in enumerate(reversed(range(len(self.messages)))):
        for i in range(len(self.messages)):
            #index = len(self.messages) - 1 - i
            y = self.window.uly + self.window.height - i - 1
            self.scr.addstr(y, self.window.ulx, self.messages[i])
            
class Dialog():
    '''
    A Dialog is a pop-up window that will show over the GameBoard when it's activated.
    It will have an ncurses Window (or panel?) as its main data member. Dialog objects
    will always (I think?) be shown modal i.e. input will not be processed by the game
    anymore, only the Dialog, until it is closed.

    This class will be curses-aware i.e. it will create the window via curses.newwin()

    NOTE: in curses, getch() is a Window function.  We *can* use the underlying window
    in Dialog objects to call .getch() while the Dialog is showing - but this does not
    really appear to be necessary.  It will just help organize the scripts that handle
    the calls to getch(). 
    '''
    def __init__(self, height, width):
        '''
        win: creates a new window using given height and width for size. Places it 
        centered in the terminal window
        '''
        self.win = curses.newwin(height, width, int((curses.LINES-height)/2), 
                int((curses.COLS-width)/2))

    # NOTE: I'm thinking you could sub-class Dialog and override the run function
    # to do something more complicated, return a value, etc.
    def run(self):
        return self.win.getch() # return the key pressed for no good reason...

    def show(self, parentwin):
        '''
        parentwin: usualy ncurses stdscr i.e. the window that is passing input control to
        this Dialog and the window that will be redrawn and shown again when the Dialog
        closes
        '''
        self.win.refresh() # once updates, if any, made. refresh to show the dialog
        # a sub-class
        self.run()
        parentwin.redrawwin()
        parentwin.refresh()

def main(stdscr):
    curses.curs_set(0)
    lst_stock_names = ["GOLD", "SILVER", "INDUSTRIAL", "BONDS", "OIL", "GRAIN"]
    gb = GameBoard(stdscr, lst_stock_names)    
    #stdscr.border()
    while True:
        key = stdscr.getch()
        gb.update_stock_price(2, 75, False)
        #stdscr.border()
        key = stdscr.getch()
        gb.update_stock_price(2, 170, True)
        key = stdscr.getch()
        gb.update_field('stockprice-0', 67)
        key = stdscr.getch()
        for i in range(10):
            gb.sa_mkt_act.add_message(f'{i} dude whats up')
        key = stdscr.getch()
        testwin = curses.newwin(20, 20, 5, 5)
        testwin.addstr(3, 3, 'TEST')
        testwin.refresh()
        key = stdscr.getch()
        stdscr.redrawwin()
        #stdscr.noutrefresh()
        #stdscr.refresh()
        #curses.doupdate()
        key = stdscr.getch()

        dlg1 = Dialog(10, 30)
        dlg1.win.box()
        dlg1.win.addstr(2, 4, 'whats up man')
        dlg1.show(stdscr)
        gb.input_chat_message()
        key = stdscr.getch()
        break

if __name__ == "__main__":
    # curses.wrapper
    curses.wrapper(main)
    for l in lst_log:
        print(l)

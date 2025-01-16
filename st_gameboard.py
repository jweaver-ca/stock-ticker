import threading
import uuid
import datetime
import queue
import curses
import curses.ascii
import textwrap
import traceback # I need to print debug logs if exception raised, but also see exception details

# for debugging only. remove when done with it
lst_log = []
def log(msg):
    lst_log.append(str(msg))

def game_operation(str_type, data):
    return {'TYPE': str_type, 'DATA': data}

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

    keys_button_nav = ( curses.KEY_UP,
        curses.KEY_DOWN,
        curses.KEY_LEFT,
        curses.KEY_RIGHT
    )

    def __init__(self, stdscr, lst_stock_names):
        self.scr = stdscr
        self.max_stock_price = 999 # no more than 3 digits!
        self.min_stock_price = 0
        self.stock_names = lst_stock_names
        self.stock_prices = [ 0 for s in lst_stock_names ]
        self.player_cash = 0
        self.player_owned = [ 0 for s in lst_stock_names ]
        self.MIN_BLOCK_SZ = 500
        self.BLOCK_SZ_DELTA = 500  # change block size by this much
        self.MAX_BLOCK_SZ = 10000
        self.buysell_block_sz = 500
        self.pending_order = [ 0 for s in lst_stock_names ]

        self.fields = dict() # Field objects
        self.coords = dict() # named coordinate locations

        self.buttongroups = dict() # key = ButtonGroup name
        self.buttongroup_first = None # ButtonGroup object ref, not name
        self.buttongroup_last = None  # ButtonGroup object ref, not name
        self.active_buttongroup = None # Name

        #TODO: concern: circular links seem wierd here...
        self.keyboard_thread = KeyboardThread('gameboard-thread', self.scr, self)
        self.game_op_event = threading.Event()
        self.game_op_queue = queue.SimpleQueue()

        # Re-entrant lock required
        self.drawlock = threading.RLock()
        self.curses_color = dict() # key=colorname, value=curses color pair
        self.program_exited = False # so we can stop the KeyboardThread

        self.init_curses_color(1, "RED", curses.COLOR_RED)
        self.init_curses_color(2, "GREEN", curses.COLOR_GREEN)

        self.scr.clear()

        # lets try a virtual window or two...
        #self.win_market = (1, 1, 11, 34) # uly, ulx, h, w
        (scry, scrx) = self.scr.getmaxyx()
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
        self.add_text(self.win_hotkey, 0, 1, '[M]essage  [R]eady  [S]ubmit Order  [P]ause  [Q]uit')

        # chatmsg - entry window for typing chat message to other players
        self.win_chatmsg = Window(self.win_hotkey.TY()-2, self.win_main.LX(), 1, self.win_main.width) 
        self.add_text(self.win_chatmsg, 0, 1, '>')
        self._add_coord('input-chat', self.win_chatmsg, 0, 3)
        width_chatmsg_in = self.win_chatmsg.RX() - self.get_coord('input-chat').X
        self.cwin_chatmsg_in = self.scr.subwin(1, width_chatmsg_in, *self.get_coord('input-chat').val())

        # sysmsg - system/game/chat messages
        height_sysmsg = self.win_chatmsg.TY()-self.win_market.BY()-3
        self.win_sysmsg = Window(self.win_market.BY()+2, self.win_main.LX(), height_sysmsg, self.win_main.width) 
        self.sa_sysmsg = ScrollArea(self.scr, self.win_sysmsg, self.drawlock)

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
        self.scr.refresh()
        #curses.doupdate() <-- probably remove this

        self.debug = False # show debugging msgs in the system message window if True

        self.keyboard_thread.start()

    def dbg(self, msg):
        '''
        Simple debugging facility, shows msg in the system message window if debugging
        enable in the GameBoard (.debug = True)
        '''
        if self.debug:
            self.add_system_msg(f"[DEBUG]: {msg}")

    def init_curses_color(self, pairnum, name, forecolor, backcolor=curses.COLOR_BLACK):
        curses.init_pair(pairnum, forecolor, backcolor)
        self.curses_color[name] = curses.color_pair(pairnum)

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

    def refresh_if(self, bln_refresh):
        if bln_refresh:
            self.scr.refresh()

    def update_stock_price(self, i_stock, new_price, bln_pays_div, bln_refresh=True):
        if new_price > self.max_stock_price:
            raise ValueError(f"[{new_price}] too high to display")
        elif new_price < self.min_stock_price:
            raise ValueError(f"[{new_price}] too low")
        char_pays_div = "✓" if bln_pays_div else " "
        self.stock_prices[i_stock] = new_price
        with self.drawlock:
            self.update_field(f'stockprice-{i_stock}', new_price, bln_refresh=False)
            self.update_field(f'stockdiv-{i_stock}', char_pays_div, bln_refresh=False)
            price_per_block = int(new_price * self.buysell_block_sz / 100)
            self.update_field(f'blockprice-{i_stock}', price_per_block, bln_refresh=False)
            if self.pending_order[i_stock] > 0:
                self.update_pending(bln_refresh=False)
            self.refresh_if(bln_refresh)

    def blocksz_change(self, data):
        if data['action'] == 'down':
            deltas = -1 * data['deltas']
        else:
            deltas = data['deltas']
        new_block_sz = self.buysell_block_sz + (deltas * self.BLOCK_SZ_DELTA)
        new_block_sz = min(new_block_sz, self.MAX_BLOCK_SZ)
        new_block_sz = max(new_block_sz, self.MIN_BLOCK_SZ)
        if new_block_sz == self.buysell_block_sz:
            return # no change, ignore (minimum enforced)
        self.buysell_block_sz = new_block_sz
        self.update_field('blocksz', self.buysell_block_sz, bln_refresh=True)

    def update_players(self, this_player_name, other_player_names, bln_refresh=True):
        '''
        Update the players participating in the game.
        called by a client program.  Following the design patter that it should
        be up to the gameboard to decide how to display the names. 
        '''
        str_players = ', '.join([this_player_name + ' (me)'] + other_player_names)
        with self.drawlock:
            self.update_field('players', str_players)
            self.refresh_if(bln_refresh)

    def update_player(self, player_cash, networth, lst_owned, bln_refresh=True):
        '''
        Update this player's attributes
        '''
        self.update_player_cash(player_cash, networth, bln_refresh=False)
        self.update_player_portfolio(lst_owned, bln_refresh=False)
        self.refresh_if(bln_refresh)

    def update_player_cash(self, player_cash, networth, bln_refresh=True):
        self.player_cash = player_cash
        self.update_field('cash', player_cash, bln_refresh=False)
        self.update_field('networth', networth, bln_refresh=False)
        self.refresh_if(bln_refresh)

    def update_player_owned(self, i_stock, shares, bln_refresh=True):
        self.player_owned[i_stock] = shares
        self.update_field(f'stockowned-{i_stock}', shares, bln_refresh)
        self.refresh_if(bln_refresh)

    def update_player_portfolio(self, lst_owned, bln_refresh=True):
        for i, owned in enumerate(lst_owned):
            if owned is not None:
                self.update_player_owned(i, owned, bln_refresh=False)
        self.refresh_if(bln_refresh)

    def update_status(self, str_status, bln_refresh=True):
        with self.drawlock:
            self.update_field('status', str_status)
            self.refresh_if(bln_refresh)

    def add_chat_msg(self, chatmsg):
        timestr = datetime.datetime.fromisoformat(chatmsg['time']).astimezone().strftime('%Y/%m/%d %H:%M:%S')
        strchat = f'[{timestr}] {chatmsg["playername"]}: {chatmsg["message"]}'
        self.add_system_msg(strchat)

    def add_system_msg(self, msg):
        self.sa_sysmsg.add_message(msg)

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
        self._add_button_group('buysell', self.update_pending_order)
        btn_names_for_nav = []
        for i, stockname in enumerate(self.stock_names):
            self.add_text(self.win_market, yoff+i, xoff, stockname)
            self._add_field(f'stockprice-{i}', self.win_market, yoff+i, xprice, len_stockprice, '>', initval=0)
            self._add_field(f'stockdiv-{i}', self.win_market, yoff+i, xdiv, 1)
            # TODO: these +/- will have to be implemented as controls soon...
            (btn_name_sell, btn_name_buy) = (f'sell-{i}', f'buy-{i}')
            self._add_button(self.buttongroups['buysell'], btn_name_sell, '-', {'action':'sell', 'stock': i}, self.win_market, yoff+i, xminus)
            self._add_button(self.buttongroups['buysell'], btn_name_buy, '+', {'action':'buy', 'stock': i}, self.win_market, yoff+i, xplus)
            btn_names_for_nav.append((btn_name_sell, btn_name_buy))
            self._add_field(f'stockowned-{i}', self.win_market, yoff+i, xowned, lenowned, initval=0, justify='>')
        for i, (btn_name_sell, btn_name_buy) in enumerate(btn_names_for_nav):
            i_next = (i+1) % len(btn_names_for_nav)
            i_prev = (i-1) % len(btn_names_for_nav)
            self.buttongroups['buysell'].set_nav(btn_name_sell, 'right', btn_name_buy)
            self.buttongroups['buysell'].set_nav(btn_name_sell, 'next', btn_name_buy)
            self.buttongroups['buysell'].set_nav(btn_name_sell, 'up', f'sell-{i_prev}')
            self.buttongroups['buysell'].set_nav(btn_name_sell, 'down', f'sell-{i_next}')
            #self.buttongroups['buysell'].set_nav(btn_name_sell, 'left', f'buy-{i_prev}')
            self.buttongroups['buysell'].set_nav(btn_name_sell, 'prev', f'buy-{i_prev}')

            #self.buttongroups['buysell'].set_nav(btn_name_buy, 'right', f'sell-{i_next}')
            self.buttongroups['buysell'].set_nav(btn_name_buy, 'next', f'sell-{i_next}')
            self.buttongroups['buysell'].set_nav(btn_name_buy, 'up', f'buy-{i_prev}')
            self.buttongroups['buysell'].set_nav(btn_name_buy, 'down', f'buy-{i_next}')
            self.buttongroups['buysell'].set_nav(btn_name_buy, 'left', btn_name_sell)
            self.buttongroups['buysell'].set_nav(btn_name_buy, 'prev', btn_name_sell)
            
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
        self.fields['pending-$'].set_curses_attr_rules(self.pending_colorer)
        self.add_text(win, ybot, midx, str_blocksz, midx, '^')
        self._add_button_group('blocksz', self.blocksz_change)
        self._add_button(self.buttongroups['blocksz'], 'blocksz-dec', '[', {'action':'down', 'deltas': 1}, win, ybot+1, midx+1)
        self._add_button(self.buttongroups['blocksz'], 'blocksz-inc', ']', {'action':'up', 'deltas': 1}, win, ybot+1, win.width-2)
        self.buttongroups['blocksz'].set_nav('blocksz-dec', 'right', 'blocksz-inc')
        self.buttongroups['blocksz'].set_nav('blocksz-dec', 'next', 'blocksz-inc')
        self.buttongroups['blocksz'].set_nav('blocksz-inc', 'left', 'blocksz-dec')
        self.buttongroups['blocksz'].set_nav('blocksz-inc', 'prev', 'blocksz-dec')
        self._add_field('blocksz', self.win_buysell, ybot+1, midx+4, 5, '>', initval=self.buysell_block_sz)
        
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
        self.sa_mkt_act = ScrollArea(self.scr, self.win_mkt_act, self.drawlock, offset=(1,2,1,3))
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

    def _add_button_group(self, name, fn_action=None):
        if name in self.buttongroups:
            raise ValueError(f"ButtonGroup '{name}' already exists")
        new_buttongroup = ButtonGroup(name, fn_action)
        old_last = self.buttongroup_last
        self.buttongroups[name] = new_buttongroup
        if self.buttongroup_first is None:
            self.buttongroup_first = new_buttongroup
            self.buttongroup_last = new_buttongroup
        else:
            old_last.buttongroup_next = new_buttongroup
            self.buttongroup_first.buttongroup_prev = new_buttongroup
            new_buttongroup.buttongroup_next = self.buttongroup_first
            new_buttongroup.buttongroup_prev = old_last
            self.buttongroup_last = new_buttongroup
            

    def _add_button(self, btn_group, name, label, data, win, y, x):
        '''
        Creates a new Button, adds it to the ButtonGroup btn_group, and draws
        it on the screen (it is non-active state)
        '''
        btn = Button(win, y, x, name, label, data, btn_group)
        btn_group.add_button(btn, name)
        self.add_text(win, y, x, label)

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

    def update_field(self, name, newval, attr=0, bln_refresh=True):
        # Field.update returns the curses.addstr args so GameBoard can draw
        addstr_args = self.fields[name].update(newval, attr, bln_refresh)
        with self.drawlock:
            self.scr.addstr(*addstr_args)
            self.scr.refresh()

    def activate_button_group(self, name):
        if self.active_buttongroup:
            curr_active = self.buttongroups[self.active_buttongroup]
            curr_active.set_active(False)
            self.update_button_group(curr_active.name)
        self.active_buttongroup = name
        self.buttongroups[name].set_active(True)
        self.update_button_group(name)

    def update_button_group(self, name):
        '''
        Redraw all the buttons in the group based on whether or not they
        are active.

        This will be called when a button navigation key is pressed so
        a new Button becomes active/inactive.
        '''
        btngrp = self.buttongroups[name]
        with self.drawlock:
            for name, btn in btngrp.buttons.items():
                if btngrp.active_button.name == name and btngrp.is_active:
                    # TODO draw as active, reverse video of its label
                    self.scr.addstr(btn.y, btn.x, btn.label, curses.A_REVERSE)
                else:
                    self.scr.addstr(btn.y, btn.x, btn.label)
            self.scr.refresh()

    def read_str(curses_win):
        # NOTE: this is a static method
        '''
        Just a wrapper to handle curses echoing, showing cursor etc while reading in a
        string from the user
        '''
        curses.echo()
        curses.curs_set(1)
        msg = curses_win.getstr()
        curses_win.erase()
        curses.curs_set(0)
        curses.noecho()
        # NOTE: refresh required to clear out the contents and hide the cursor, etc
        curses_win.refresh()
        
        return msg

    def display_die_roll(self, roll_data, bln_refresh=True):
        with self.drawlock:
            self.sa_mkt_act.add_message(f'{self.stock_names[roll_data["stock"]]} {roll_data["action"]} {roll_data["amount"]}')
            self.refresh_if(bln_refresh)

    def display_split_message(self, split_data, bln_refresh=True):
        stock = self.stock_names[split_data['stock']]
        gained = split_data['gained']
        with self.drawlock:
            self.sa_sysmsg.add_message(f'{stock} has split!  You earned {gained} shares')
            self.refresh_if(bln_refresh)

    def display_bust_message(self, bust_data, bln_refresh=True):
        stock = self.stock_names[bust_data['stock']]
        lost = bust_data['lost']
        with self.drawlock:
            self.sa_sysmsg.add_message(f'{stock} has gone off the market!  You lost {lost} shares')
            self.refresh_if(bln_refresh)
        
    def input_chat_message(self):
        # NOTE: getstr really has to go in a curses window proper, else the entry
        #   ruins stuff to the right that's in the same window
        chat_msg = GameBoard.read_str(self.cwin_chatmsg_in).decode('utf-8')
        # NOTE/TODO: adding redrawwin call here to see if it helps with an issue noticed
        #   after sending a message and the screen goes wonky.
        #   if this doesn't fix it, the call should be removed
        self.scr.redrawwin()
        return chat_msg
        # TODO: actually send the dang message

    def pending_order_cost(self):
        cost_cents = 0
        for i_stock, shares in enumerate(self.pending_order):
            cost_cents += self.stock_prices[i_stock] * shares
        return int(cost_cents / 100)

    def reset_pending_order(self):
        with self.drawlock:
            for i in range(len(self.stock_names)):
                self.pending_order[i] = 0
                self.update_field(f'pending-{i}', self.pending_order[i], bln_refresh=False)
            self.update_pending(bln_refresh=False)
            self.refresh_if(True)

    def update_pending(self, bln_refresh=True):
        ''' called to reflect new market prices '''
        self.update_field(f'pending-$', -self.pending_order_cost())
        self.refresh_if(bln_refresh)

    def update_pending_order(self, order_data):
        ''' Called by clicking a buysell button '''
        i_stock = order_data['stock']
        share_count = self.buysell_block_sz
        if order_data['action'] == 'buy':
            current_cost = self.pending_order_cost()
            extra_cost = int(self.stock_prices[i_stock] * share_count / 100)
            projected_total = current_cost + extra_cost
            if projected_total > self.player_cash:
                self.dbg(f'cant afford it: {self.player_cash=} {current_cost=} {extra_cost=} {projected_total=}')
                return # cant afford it, ignore
            share_total = self.pending_order[i_stock] + share_count 
        elif order_data['action'] == 'sell':
            # sell here can really mean either 'lower the buy' or 'sell' if current pending <= 0
            if self.player_owned[i_stock] + (self.pending_order[i_stock] - share_count) < 0:
                self.dbg(f'below zero bro: {self.pending_order=} {share_count=} owned={self.player_owned[i_stock]}')
                return # not enough stock, ignore
            share_total = self.pending_order[i_stock] - share_count 
        self.pending_order[i_stock] = share_total
        with self.drawlock:
            self.update_field(f'pending-{i_stock}', share_total, bln_refresh=False)
            new_projected_total = self.pending_order_cost()
            self.update_field(f'pending-$', -new_projected_total, bln_refresh=False)
            self.refresh_if(True)

    def buysell_approval(self, data):
        if data['approved']:
            lst_summary = []
            for i,(shares, cost) in enumerate(data['order']):
                if shares != 0:
                    lst_summary.append(f"{self.stock_names[i]} {shares:+}")
            str_summary = ', '.join(lst_summary)
            self.add_system_msg(f'BuySell order approved: {str_summary}')
        else:
            self.add_system_msg(f'BuySell order REJECTED: {data["reject-reason"]}')
        self.reset_pending_order()

    def report_div(self, i_stock, earned):
        self.add_system_msg(f'{self.stock_names[i_stock]} dividend earned you ${earned}!')

    def buysell_operation(self):
        '''Create operation based on pending_order and current prices'''
        # TODO: track reqid make sure it gets answered?? any reason why/why not?
        reqid = str(uuid.uuid4())
        order_data = []
        for i, shares in enumerate(self.pending_order):
            curprice = self.stock_prices[i]
            order_data.append((shares, curprice))
        if not all(x[0]==0 for x in order_data):
            return {'reqid': reqid, 'data': order_data}
        return None

    def nav(self, motion):
        '''
        GameBoard.nav
        Called when a direction key is pressed to update whatever the currently
        active ButtonGroup. If no active ButtonGroup, just ignore.
        '''
        if self.active_buttongroup:
            self.buttongroups[self.active_buttongroup].nav(motion)
            self.update_button_group(self.active_buttongroup)

    def buttongroup_nav(self, motion):
        if motion not in ('prev', 'next'):
            raise ValueError(f"Invalid motion: [{motion}]")
        if self.active_buttongroup:
            curr_active = self.buttongroups[self.active_buttongroup]
            if motion == 'prev':
                next_active = curr_active.buttongroup_prev
            elif motion == 'next':
                next_active = curr_active.buttongroup_next
            self.dbg(f'next_active: {next_active.name}')
            if curr_active.name == next_active.name:
                self.dbg(f'no next active found')
                return # nothing to do, there is no 'next'...
            self.activate_button_group(next_active.name)
        else:
            self.activate_button_group(self.buttongroup_first.name)

    def get_operation(self, block=True, timeout=5):
        ''' Client calls this to get the next action requested by player'''
        try:
            retval = self.game_op_queue.get(block=block,timeout=timeout)
        except queue.Empty as e:
            return None
        return retval

    def redraw(self):
        self.scr.redrawwin()

    def pending_colorer(self, val):
        try:
            ival = int(val)
            if ival > 0:
                return self.curses_color["GREEN"]
            elif ival < 0:
                return self.curses_color["RED"]
        except:
            pass
        return 0

    def keyboard_handler(curses_key):
        ckey = chr(key)
        #self.add_system_msg(f'KEYPRESS: {key}')
        if key in self.keys_button_nav:
            if self.active_buttongroup is not None:
                nav_lookup = {
                    curses.KEY_UP: 'up',
                    curses.KEY_DOWN: 'down',
                    curses.KEY_RIGHT: 'right',
                    curses.KEY_LEFT: 'left'
                }
                self.nav(nav_lookup[key])
            else:
                self.dbg('no active button group')
        #NOTE: cant find a good curses way to read TAB...
        elif key == curses.ascii.TAB:
            self.buttongroup_nav('next')
        elif key == curses.KEY_STAB:
            self.buttongroup_nav('prev')
        elif ckey in ('q', 'Q'):
            #self.running = False
            self.game_op_queue.put(game_operation('quit', None))
            self.running = False # when we know for sure we want to exit, stop the loop
        elif ckey in ('m', 'M'):
            # TODO: how do we send the damn message????
            str_msg = self.input_chat_message()
            if (str_msg):
                self.game_op_queue.put(game_operation('chat-message', str_msg))
        elif ckey in ('f', 'F'):
            self.add_system_msg('redraw requested')
            self.redraw()
            self.scr.refresh()
            curses.doupdate()
        elif ckey in ('r', 'R'):
            # request to start game (basically "I'm ready" message to server)
            self.game_op_queue.put(game_operation('ready-start', None))
            # TODO: add an operation to the game_op_queue
        elif ckey in ('p', 'P'):
            self.add_system_msg('Pause requested: not implemented')
        elif ckey in ('s', 'S'):
            op_data = self.buysell_operation()
            if op_data: # None if no pending order
                self.game_op_queue.put(game_operation('buysell', op_data))
        elif key in (curses.ascii.SP, curses.ascii.CR):
            if not self.active_buttongroup:
                self.dbg('click but no active button group')
                continue
            btn = self.buttongroups[self.active_buttongroup].get_active_button()
            btn.click()

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
        self.fn_curses_attr = None

    # TODO: should not draw, should return the addstr args to GameBoard
    def update(self, newval, attr=0, bln_refresh=True):
        str_newval = str(newval)
        if len(str_newval) > self.length:
            raise ValueError(f"newval [{newval}] too long for this Field")
        str_fullval = f"{str_newval:{self.justify}{self.length}s}"
        if self.fn_curses_attr:
            attr = self.fn_curses_attr(newval)
        return (self.y, self.x, str_fullval, attr)

    def set_curses_attr_rules(self, fn_rules):
        self.fn_curses_attr = fn_rules

class ScrollArea(object):
    '''
    Simple upwards scroll area (starts at bottom)
    Lines are split according to width of the given window
    '''
    def __init__(self, scr, window, drawlock, offset=None):
        '''
        scr: curses window (from GameBoard)
        window: Window where this will go
        offset: tuple (left,up,right,down), if not given, all zeros (whole window)
        drawlock: drawing lock provided by GameBoard to synchronize drawing
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
        self.drawlock = drawlock
        self.window = Window(window.uly+offset[1], window.ulx+offset[0], thisheight, thiswidth)
        self.firsty = self.window.uly + self.window.height # bottom line (first)


    def add_message(self, str_message):
        #TODO: find a better/efficient way to clear lines besides formatting the string to fill with spaces on the right
        #      mostly its just confusing why this formatting is done...
        lst_msg = [ f"{x:<{self.window.width}}" for x in textwrap.wrap(str_message,width=self.window.width)][::-1]
        self.messages = lst_msg + self.messages[:self.window.height-len(lst_msg)]
        with self.drawlock:
            for i in range(len(self.messages)):
                #index = len(self.messages) - 1 - i
                y = self.window.uly + self.window.height - i - 1
                self.scr.addstr(y, self.window.ulx, self.messages[i])
            self.scr.refresh()
            
class Dialog():
    '''
    A Dialog is a pop-up window that will show over the GameBoard when it's
    activated via show().  It will have an ncurses Window (or panel?) as its main
    data member. Dialog objects will always (I think?) be shown modal i.e.
    input will not be processed by the game anymore, only the Dialog, until it
    is closed. It will always show centered in the screen

    This class will be curses-aware i.e. it will create the window via curses.newwin()
    All Dialogs will be made of two curses windows: one for the padding/border, and the 
    main window inside that which will have dynamic content.

    borders and padding extend the area of the window past the given height, width in
    the constructor. 1-char wide padding along x-axis is always added so with a border
    the window will be 2 chars wider than given width

    NOTE: in curses, getch() is a Window function.  We *can* use the underlying window
    in Dialog objects to call .getch() while the Dialog is showing - but this does not
    really appear to be necessary.  It will just help organize the scripts that handle
    the calls to getch(). 
    '''
    def __init__(self, height, width, border=True):
        '''
        win: creates a new window using given height and width for size. Places it 
        centered in the terminal window
        border: if True, creates a border around the window increasing the true dimensions
            of the window by 2 each way
        '''
        w_border = 1 if border else 0
        yx_pad = (0, 1) # NOTE: might make this adjustable in future
        fulldim = (height + (w_border*2) + (yx_pad[0]*2), width + (w_border*2) + (yx_pad[1]*2))
        fullpos = ( int((curses.LINES-(fulldim[0]))/2), int((curses.COLS-(fulldim[1]))/2) )
        self.fullwin = curses.newwin(*fulldim, *fullpos)
        if border:
            pos = (w_border + yx_pad[0], w_border + yx_pad[1])
            self.fullwin.box()
            self.win = self.fullwin.derwin(height, width, *pos)
        else:
            self.win = self.fullwin.derwin(height, width, *yx_pad)
        self.fullwin.refresh() # required to draw border/padding
        self.dlg_val = None  # Dialogs will always be able to return a value

    # NOTE: I'm thinking you could sub-class Dialog and override the run function
    # to do something more complicated, return a value, etc.
    def run(self):
        # NOTE: if self.win doens't have keypad(True) set then arrow keys (for eg) will
        #       will have no effect
        return self.win.getch() # return the key pressed for no good reason...

    def show(self, parentwin):
        '''
        parentwin: usualy ncurses stdscr i.e. the window that is passing input control to
        this Dialog and the window that will be redrawn and shown again when the Dialog
        closes
        '''
        # TODO-CONCERN: prove win.refresh() is enough to show dialog properly always
        self.win.refresh() # once updates, if any, made. refresh to show the dialog
        # a sub-class
        self.dlg_val = self.run()
        parentwin.redrawwin()
        parentwin.refresh()
        return self.dlg_val

class TextInputDialog(Dialog):
    '''
    subclass of Dialog specifically meant for getting a small string value from
    the user (e.g. username, server-host, etc)

    height is determined automatically by divding up the given prompt according
    to width, and making room for the input, etc
    '''
    def __init__(self, prompt, dlg_width, input_len, border=True, validation=None):
        # break up the prompt according to dlg_width
        lst_prompt = textwrap.wrap(prompt, dlg_width)
        height = len(lst_prompt) + 2
        super().__init__(height, dlg_width, border)
        for i, prompt_part in enumerate(lst_prompt):
            self.win.addstr(i, 0, prompt_part)
        self.win_input = self.win.derwin(1, input_len, height-1, 0)
        self.win_input.bkgd('_')

    def run(self):
        return GameBoard.read_str(self.win_input).decode('utf-8')

class Button():
    '''
    A Button is a single char on the gameboard that when 'clicked' will fire an 
    associated action.  The GameBoard can only have one Button 'active' at a time
    which is indicated by reverse video (highlighted). Pressing <space> or <enter>
    'clicks' the GameBoard's currently active Button if there is one.

    A Button's action is determined by callable fn_action, or if not given, the 
    action of the ButtonGroup to which it belongs.  'data' is passed as 

    arrow keys can select the 'next' button in the ButtonGroup.  Only one ButtonGroup
    can be active at a time. A ButtonGroup will need to be activated by a hot key.
    '''
    def __init__(self, win, y, x, name, label, data, btn_group, fn_action=None):
        '''
        data: this button's argument(s) for the action
        label: the char or str showing on the screen
        btn_group: the ButtonGroup this Button belongs to (required if Button doesn't have
            its own action assigned to it)
        '''
        self.y = win.uly+y
        self.x = win.ulx+x
        self.data = data
        self.name = name
        self.label = str(label)
        self.group = btn_group
        self.set_action(fn_action)

    def click(self):
        if self.action is None:
            if self.group.action is None:
                raise ValueError("Action has not been set")
            else:
                self.group.action(self.data)
        else:
            self.action(data)

    def set_action(self, fn_action):
        self.action = fn_action

class ButtonGroup():
    '''
    The gameboard will manage button groups. The ButtonGroup objects will manage
    the individual Buttons. When a user 'clicks' the button-activate key (space,
    enter) the active ButtonGroup's active Button will get the click.

    GameBoard will track if a ButtonGroup is active, but the ButtonGroup object itself
    will track which button within it is active.

    Concepts: 
    GameBoard will not interact with ButtonGroup using button names, only through
    navigation (left, right, up, down, next?) and pressing/clicking
    '''
    NAV_VALS = ('up', 'down', 'left', 'right', 'prev', 'next')

    def __init__(self, name, fn_action=None):
        self.name = name
        self.action = fn_action
        self.buttons = dict()
        self.active_button = None # object ref, not name
        self.is_active = False
        self.nav_info = dict() # key = Button name
        self.buttongroup_next = None # object, not name
        self.buttongroup_prev = None

    def add_button(self, btn, name):
        if name in self.buttons:
            raise ValueError(f"Button {name} already in ButtonGroup")
        self.buttons[name] = btn
        self.nav_info[name] = {x: None for x in ButtonGroup.NAV_VALS}
        if self.active_button is None:
            self.active_button = btn
   
    # TODO/suspect: get/set_active_button probably not needed
    def get_active_button(self):
        return self.active_button

    def active_button_name(self):
        if self.active_button:
            return self.active_button

    def set_active_button(self, btn_name):
        self.active_button = self.buttons[btn_name]

    def set_active(self, bln_active):
        self.is_active = bln_active
   
    def set_nav(self, btn_from_name, motion, btn_to_name):
        if motion not in ButtonGroup.NAV_VALS:
            raise ValueError(f"bad motion: [{motion}]")
        self.nav_info[btn_from_name][motion] = btn_to_name

    def nav(self, direction):
        #TODO:  apply navigation
        #    set which is active, redraw?? prolly no
        if not self.is_active:
            raise ValueError(f"attempt to navigate inactive ButtonGroup")
        new_active_btn_name = self.nav_info[self.active_button.name][direction]
        if new_active_btn_name:
            self.active_button = self.buttons[new_active_btn_name]

# NOTE: I think the mechanics of KeyboardThread should be merged into
#  GameBoard. I think that makes sense since GameBoard has the hotkeys
# etc.
class KeyboardThread(threading.Thread):
    def __init__(self, name, scr, handler, daemon=True):
        super().__init__(name=name)
        self.scr = scr
        self.hander = handler
        self.msg = ""
        self.daemon = True
        self.running = False

    def set_scr(self, scr):
        self.scr = scr

    def set_handler(self, handler):
        self.handler = handler

    def run(self):
        self.running = True
        self.scr.timeout(1000)
        while self.running:
            # does not block (?) if scr.timeout > 0
            key = self.scr.getch() # blocking (since curses.nodelay() not called)
            if key == -1:
                if self.gameboard.program_exited:
                    self.running = False
                continue
            handler(key)
        # end of while loop, to get here means program is exiting
                
    def stop(self):
        self.running = False

class LobbyBoard():
    def __init__(self, scr):
        self.border = scr
        self.border.box()
        self.border.refresh()
        x, x = (i-2 for i in scr.getmaxyx())
        self.scr = self.border.derwin(y, x, 1, 1)
        self.scr.erase()
        self.scr.box()
        self.scr.refresh()

        self.scr.addstr(

    def 

def main(stdscr):
    curses.curs_set(0)
    lst_stock_names = ["GOLD", "SILVER", "INDUSTRIAL", "BONDS", "OIL", "GRAIN"]
    gb = GameBoard(stdscr, lst_stock_names)    
    gb.debug = True
    #stdscr.border()
    gb.activate_button_group('buysell')
    while True:
        key = stdscr.getch()
        if key in gb.keys_button_nav:
            if gb.active_buttongroup is not None:
                nav_lookup = {
                    curses.KEY_UP: 'up',
                    curses.KEY_DOWN: 'down',
                    curses.KEY_RIGHT: 'right',
                    curses.KEY_LEFT: 'left'
                }
                gb.dbg(f'nav key: {key} -> [{nav_lookup[key]}]')
                gb.nav(nav_lookup[key])
            else:
                gb.dbg('no active button group')
            continue
        #NOTE: cant find a good curses way to read TAB...
        elif key == 9:
            gb.dbg('got tab key')
            gb.buttongroup_nav('next')
            continue
        gb.dbg(f'key: {key}')
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

        dlg1 = Dialog(10, 30, border=True)
        #dlg1 = Dialog(10, 30)
        dlg1.win.addstr(2, 4, 'whats up man')
        val = dlg1.show(stdscr)
        gb.add_system_msg(f"dlg got: {val}")
        chat_msg = gb.input_chat_message()
        key = stdscr.getch()
        prompt = 'Please enter your name:'
        dlg2 = TextInputDialog(prompt, 40, 20)
        name = dlg2.show(stdscr)
        gb.add_system_msg(f"Name entered: {name}")
        key = stdscr.getch()
        break

if __name__ == "__main__":
    # curses.wrapper
    if False:
        try:
            curses.wrapper(main)
        except:
            traceback.print_stack()
        finally:
            for l in lst_log:
                print(l)
    else:
        # for when I need the stack trace more than the logs...
        # TODO: figure out how to get BOTH...
        curses.wrapper(main)
        for l in lst_log:
            print(l)

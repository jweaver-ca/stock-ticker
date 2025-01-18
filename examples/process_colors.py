# process strings that contain escape sequences for color
# for curses, this means breaking up a string into pieces, each piece
# having the color_pair attribute attached to it, along with the x value
# of where it should start on the screen.

# e.g. "The <c:1>quick</c> <c:2r>brown</c> fox died", x = 0 
#       012345678901234567890123
# e.g. "The quick brown fox died"
# returns ((0, "The ", curses.A_NORMAL),
#          (4, "quick", curses.color_pair(1)),
#          (9, " ", curses.A_NORMAL),
#          (10, "brown", curses.color_pair(2) | curses.A_REVERSE),
#          (15, " fox died", curses.A_NORMAL))

import curses
import re
re_escape = re.compile(r'<c:(\d+)(r)?>')
end_flag = "</c>"

def process_colors(str_value, start_attr=None):
    retval = []
    curr_x = 0
    curr_attr = start_attr
    if type(str_value) == str:
        while str_value:
            str_value_init = str_value
            # at start of loop, we have always just started or removed an end
            #   flag or found the start of the next flag
            # first, figure out if end flag or next start flag is closer
            i_end = len(str_value)+1 if curr_attr is None else str_value.find(end_flag)
            i_nextstart = -1
            if m := re_escape.search(str_value):
                i_nextstart = m.start()
            else:
                i_nextstart = len(str_value)+1
            if i_end == -1 and i_nextstart == -1:
                # neither was found, end it
                retval.append((curr_x, str_value, curr_attr))
                return retval
            i = min(i_end, i_nextstart)
            #i = max(n for n in (i_end, i_nextstart) if n > -1)
            print (f"{str_value}\n  {i=} {i_end=} {i_nextstart=}")
            if i == i_end:
                # currently might have an attribute and found an end flag
                retval.append((curr_x, str_value[0:i], curr_attr))
                str_value = str_value[i_end+len(end_flag):]
                curr_x += i
                curr_attr = None
            elif i == i_nextstart:
                if i > 0:
                    retval.append((curr_x, str_value[0:i], curr_attr))
                    str_value = str_value[m.start():]
                else:
                    curr_attr = "curses.init_pair({m.group(1)})"
                    str_value = str_value[m.end():]
                curr_x += i
            else:
                raise ValueError("didnt expect to get here")
            if str_value == str_value_init:
                raise ValueError(f'no change: {str_value=}')
        return retval
                    
            
#           #print (m.start())
#           # TODO: not a string when real obvs duh
#           if m.start() > 0:
#               retval.append((curr_x, str_value[0:m.start()], curses.A_NORMAL))
#           attr = f"curses.color_pair({m.group(1)})"
#           str_value = [m.end():]
#           curr_x = m.start()
#           i_end = str_value.find(end_flag)
#           i_nextstart = -1
#           if m := re_escape.search(str_value):
#               if m.start() > i_end:
#                   i_next_start = m.start()
#           if i_end >= 0:
#               # see if the next being escape is closer
#
#                       retval.append((curr_x, str_value[0:m.start()
#                   
#       else:
#           print ('no match')
#       return retval
    else: # iterable, return list of results
        # TODO: start the next iteration with end of previous ones attr
        retval = []
        curr_attr = start_attr
        for inner_str_value in str_value:
            retval.append(process_colors(str(inner_str_value)))
        return retval

if __name__ == '__main__':    
    s = "The <c:1>quick</c> <c:2r>brown</c> fox died"
    for part in process_colors(s):
        print (part)

# e.g. 

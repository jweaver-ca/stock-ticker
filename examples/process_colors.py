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
re_escape = re.compile(r'<c:(\d+)([a-z]*)>')
end_flag = "</c>"

def process_colors(str_value, start_attr=None):
    retval = []
    curr_x = 0
    curr_attr = start_attr
    if type(str_value) == str:
        tmp_str_value = str_value # copy, not ref, edits while processing
        while tmp_str_value:
            str_value_init = tmp_str_value # see if anything changed (for debugging)
            # at start of loop, we have always just started or removed an end
            #   flag or found the start of the next flag
            # first, figure out if end flag '</c>' or next start flag is closer
            # i_end: index of start of '</c>'
            #        - attr is None means not processing a tag, so not looking for it
            #        - if not found at all, pretend it's the end of the string
            i_end = len(tmp_str_value)+1 if curr_attr is None else tmp_str_value.find(end_flag)
            if m := re_escape.search(tmp_str_value):
                i_nextstart = m.start()
            else:
                i_nextstart = -1
            if i_end == -1 and i_nextstart == -1:
                # neither was found, end it
                retval.append((curr_x, tmp_str_value, curr_attr))
                return retval
            # exclude any -1 values from min()
            minargs = (i for i in (i_end, i_nextstart) if i > -1)
            i = min(minargs)
            #print (f"{tmp_str_value}\n  {i=} {i_end=} {i_nextstart=}")
            if i == i_end:
                # currently might have an attribute and found an end flag
                retval.append((curr_x, tmp_str_value[0:i], curr_attr))
                tmp_str_value = tmp_str_value[i_end+len(end_flag):]
                curr_x += i
                curr_attr = None
            elif i == i_nextstart:
                if i > 0:
                    retval.append((curr_x, tmp_str_value[0:i], curr_attr))
                    tmp_str_value = tmp_str_value[m.start():]
                else:
                    pair_num = m.group(1)
                    curr_attr = f"curses.color_pair({pair_num})"
                    tmp_str_value = tmp_str_value[m.end():]
                    if m.lastindex > 1: # has modifiers e.g. "r"
                        # for loop in case we add more modifiers one day
                        for modifier in m.group(2):
                            if modifier == 'r':
                                curr_attr += "|curses.A_REVERSE"
                            #elif: etc, in future
                            else:
                                raise ValueError(f"bad modifier {modifier} in {str_value}")
                curr_x += i
            else:
                raise ValueError("didnt expect to get here")
            if tmp_str_value == str_value_init:
                raise ValueError(f'no change: {str_value=}')
        return retval
                    
            
    else: # iterable, return list of results
        # TODO: start the next iteration with end of previous ones attr
        retval = []
        curr_attr = start_attr
        for inner_str_value in str_value:
            retval.append(process_colors(str(inner_str_value)))
        return retval

def pc_test(strval, expected_result, bln_print_result=False):
    print (f"TEST:{strval}")
    retval = process_colors(strval)
    bln_anyfailures = False
    bln_PASS = (retval == expected_result)
    if bln_PASS:
        print (" ** PASS **")
    else:
        print (" ** FAIL **")
    if bln_print_result:
        print (',\n'.join(str(x) for x in retval))
    return bln_PASS

if __name__ == '__main__':    
    print_results = True
    test_strs = [
        ("The <c:1>quick</c> <c:2r>brown</c> fox died",
            [(0, 'The ', None),
            (4, 'quick', 'curses.color_pair(1)'),
            (9, ' ', None),
            (10, 'brown', 'curses.color_pair(2)|curses.A_REVERSE'),
            (15, ' fox died', None)]
        ),
        ("<c:3r>Hello<c:2> dude",
            [(0, 'Hello', 'curses.color_pair(3)|curses.A_REVERSE'),
            (5, ' dude', 'curses.color_pair(2)')]
        ),
        ("<c/>dude <c:a><c:5></c><c:3>hello</c>",
        # should ignore and just print the malformed tags
        # also WILL add zero length sections. up to caller to not do stupid stuff like that
            [
                (0, '<c/>dude <c:a>', None),
                (14, '', 'curses.color_pair(5)'),
                (14, 'hello', 'curses.color_pair(3)')
            ]
        )
    ]
    bln_anyfailures = False
    for s in test_strs:
        bln_pass = pc_test(s[0], s[1], print_results)
        if not bln_pass:
            bln_anyfailures = True
    if bln_anyfailures:
        print ("THERE WERE FAILURES")

# e.g. 

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
import textwrap

class ColorProcessor():
    def __init__(self):
        self.re_escape = re.compile(r'<c:(\d+)([a-z]*)>')
        self.end_flag = "</c>"

    def process_colors(self, str_value, width=None, start_attr=None):
        retval = []
        curr_x = 0
        curr_attr = start_attr
        tmp_str_value = str_value # copy, not ref, edits while processing
        while tmp_str_value:
            str_value_init = tmp_str_value # see if anything changed (for debugging)
            # at start of loop, we have always just started or removed an end
            #   flag or found the start of the next flag
            # first, figure out if end flag '</c>' or next start flag is closer
            # i_end: index of start of '</c>'
            #        - attr is None means not processing a tag, so not looking for it
            #        - if not found at all, pretend it's the end of the string
            i_end = len(tmp_str_value)+1 if curr_attr is None else tmp_str_value.find(self.end_flag)
            if m := self.re_escape.search(tmp_str_value):
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
                tmp_str_value = tmp_str_value[i_end+len(self.end_flag):]
                curr_x += i
                curr_attr = None
            elif i == i_nextstart:
                if i > 0:
                    retval.append((curr_x, tmp_str_value[0:i], curr_attr))
                    tmp_str_value = tmp_str_value[m.start():]
                else:
                    pair_num = int(m.group(1))
                    curr_attr = curses.color_pair(pair_num)
                    tmp_str_value = tmp_str_value[m.end():]
                    if m.lastindex > 1: # has modifiers e.g. "r"
                        # for loop in case we add more modifiers one day
                        for modifier in m.group(2):
                            if modifier == 'r':
                                curr_attr |= curses.A_REVERSE
                            #elif: etc, in future
                            else:
                                raise ValueError(f"bad modifier {modifier} in {str_value}")
                curr_x += i
            else:
                raise ValueError("didnt expect to get here")
            if tmp_str_value == str_value_init:
                raise ValueError(f'no change: {str_value=}')
        if width is not None:
            return self.wrap_lines(retval, width)
        else:
            return retval

    def wrap_lines(self, lst_parts, width):
        thisx = 0 # current x value of this retval item, each line starts at 0
        retval = [ [] ]
        i_retval = 0 # retval index we are currently building
        i_parts = 0 # index of lst_parts currently processing
        skiplen = 0 # when we process the same lst_parts item again, this is how much we should skip
        this_retval_plaintext = "" # build this for seeing where textwrap will break up the line

        last_text = "" # for debugging, remove when proved ok
        last_i_parts = -1 # for debugging, remove when proved ok

        while i_parts < len(lst_parts):
            (x, text, attr) = lst_parts[i_parts]
            text = text[skiplen:]
            if thisx == 0:
                # remove any spaces at the start since this is start of a new line
                text = re.sub(r'^\s*', '', text)
            if last_text == text and last_i_parts == i_parts:
                raise ValueError("no")
            last_text = text
            last_i_parts = i_parts
            # 1. entire part fits into line
            if thisx + len(text) <= width:
                if len(text) > 0:
                    retval[i_retval].append((thisx, text, attr))
                    thisx += len(text)
                    i_parts += 1 # start next part
                    skiplen = 0
                    this_retval_plaintext += text
            else:
                # got to break it up
                # append what we can, remove it from this part and reprocess it on next line
                # i_lst_parts will *not* increment
                plaintext_parts = textwrap.wrap(this_retval_plaintext + text, width)
                i_wrap = len(plaintext_parts[0])
                i_wrap_text = i_wrap - len(this_retval_plaintext)
                if i_wrap_text > 0:
                    retval[i_retval].append((thisx, text[0:i_wrap_text], attr))
                retval.append([])
                this_retval_plaintext = ""
                i_retval += 1
                thisx = 0
                skiplen += i_wrap_text
        return retval
                
def cp_test(cp, strval, width, expected_result, bln_print_result=False):
    print (f"TEST:{strval} {width=}")
    retval = cp.process_colors(strval, width)
    bln_anyfailures = False
    bln_PASS = (retval == expected_result)
    if bln_PASS:
        print (" ** PASS **")
    else:
        print (" ** FAIL **")
    if bln_print_result:
        print (',\n'.join(str(x) for x in retval))
    return bln_PASS

def main(stdscr):
    print_results = True
    cp = ColorProcessor()
    test_strs = [
        ("The <c:1>quick</c> <c:2r>brown</c> fox died", None,
            [(0, 'The ', None),
            (4, 'quick', curses.color_pair(1)),
            (9, ' ', None),
            (10, 'brown', curses.color_pair(2)|curses.A_REVERSE),
            (15, ' fox died', None)]
        ),
        ("<c:3r>Hello<c:2> dude", None,
            [(0, 'Hello', curses.color_pair(3)|curses.A_REVERSE),
            (5, ' dude', curses.color_pair(2))]
        ),
        ("<c/>dude <c:a><c:5></c><c:3>hello</c>", None,
        # should ignore and just print the malformed tags
        # also WILL add zero length sections. up to caller to not do stupid stuff like that
            [
                (0, '<c/>dude <c:a>', None),
                (14, '', curses.color_pair(5)),
                (14, 'hello', curses.color_pair(3))
            ]
        ),
        ("The <c:1>quick brown</c> fox died", 10,
            [
                [
                    (0, 'The ', None), 
                    (4, 'quick', curses.color_pair(1))
                ], 
                [   (0, 'brown', curses.color_pair(1)), 
                    (5, ' fox', None)
                ], 
                [
                    (0, 'died', None)
                ]
            ]
        ),
        ("The <c:1>quick brown</c> fox died", 15,
            [ [(0, 'The ', None), (4, 'quick brown', curses.color_pair(1))],
            [(0, 'fox died', None)] ]
        ),
        ("The<c:1>quickbrown</c>foxd<c:2>ied how about</c> that", 12,
            [
                [(0, 'The', None), (3, 'quickbrow', curses.color_pair(1))],
                [(0, 'n', curses.color_pair(1)), (1, 'foxd', None), (5, 'ied how', curses.color_pair(2))],
                [(0, 'about', curses.color_pair(2)), (5, ' that', None)]
            ]
        )
    ]
    bln_anyfailures = False
    for test_str, width, expected_result in test_strs:
        bln_pass = cp_test(cp, test_str, width, expected_result, print_results)
        if not bln_pass:
            bln_anyfailures = True
    if bln_anyfailures:
        print ("THERE WERE FAILURES")

if __name__ == '__main__':    
    curses.wrapper(main)

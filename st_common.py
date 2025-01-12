# classes common to client and server programs
import struct
import json

# MessageReceiver objects just receive bytes over a network connection and form them into
# messages.  Actions by these objects are triggered by selector events
# NOTE: this was called 'ChatClient' which is/was a terrible name...
# TODO: update st_server.py to import and use
class MessageReceiver:
    def __init__(self, name, conn, fn_processor):
        '''
        name: just a string - currently not used
        conn: tcp/ip connection
        fn_processor: callable for processing messages once received
        '''
        self.conn = conn
        self.name = name
        self.processor = fn_processor

        self.remaining_sz_bytes = 4
        self.sz_bytes = b''
        self.sz = 0                  # size of message in bytes
        self.msg = b''               # bytes of message being received
        self.message = None          # completed message object once all received

    # called when bytes received over connection conn.  When a message is completed, process it
    # message starts with 4 byte int indicating size, then that # of bytes for
    # message body
    def add_bytes(self, b):
        print (f'add_bytes: {b}')
        while b: # always substract from byte array as its processed
            if self.kt:
                # NOTE/TODO: kt is just for debugging?  there's got to be a better solution!
                self.kt.scr.addstr(f'{b}\n')
                self.kt.scr.refresh()
            if self.remaining_sz_bytes > 0:
                self.sz_bytes += b[0:self.remaining_sz_bytes]
                b = b[self.remaining_sz_bytes:]
                self.remaining_sz_bytes = 4 - len(self.sz_bytes)
                if len(self.sz_bytes) == 4:
                    self.sz = struct.unpack('I', self.sz_bytes)[0]
            if b:
                if len(b) + len(self.msg) < self.sz:
                    # not enough data in b to complete message
                    self.msg += b
                    b = b'' # stop loop
                else:
                    # exactly enough or extra
                    required_bytes = self.sz - len(self.msg)
                    self.msg += b[0:required_bytes]
                    # TODO: process message
                    print(f'self.msg: {self.msg}')
                    self.message = json.loads(self.msg.decode('utf-8'))
                    #process_message(self)
                    self.processor(self.message)
                    b = b[required_bytes:]
                    self.sz_bytes = b''
                    self.remaining_sz_bytes = 4
                    self.msg = b''
                    self.sz = 0
                    self.message = None

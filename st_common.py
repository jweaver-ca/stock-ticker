# classes common to client and server programs
import struct
import json
import queue

# MessageReceiver objects just receive bytes over a network connection and form them into
# messages.  Actions by these objects are triggered by selector events
# NOTE: this was called 'ChatClient' which is/was a terrible name...
# TODO: update st_server.py to import and use
class MessageReceiver:
    def __init__(self, name, conn, fn_processor=None):
        '''
        name: just a string - currently not used
        conn: tcp/ip connection
        fn_processor: callable for processing messages once received

        If fn_processor is not provided, the MessageReceiver will store the messages in queue
        that can be accessed with get_message() which blocks until a message becomes available

        It's not intended that you should be able to add fn_processor after initialization. I would
        not recommend you do that.
        '''
        self.conn = conn
        self.name = name
        self.processor = fn_processor
        if fn_processor is None:
            self.queue = queue.SimpleQueue()

        self.remaining_sz_bytes = 4
        self.sz_bytes = b''
        self.sz = 0                  # size of message in bytes
        self.msg = b''               # bytes of message being received
        self.message = None          # completed message object once all received
        self.data = None             # optionally send this as extra arg to fn_processor

        self.kt = None # TODO remove this altogether, just here to avoid exception

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
                    if self.processor is not None:
                        if self.data:
                            self.processor(self.message, data)
                        else:
                            self.processor(self.message)
                    else:
                        self.queue.put(self.message)
                    b = b[required_bytes:]
                    self.sz_bytes = b''
                    self.remaining_sz_bytes = 4
                    self.msg = b''
                    self.sz = 0
                    self.message = None

    def get_message(self):
        if self.processor is not None:
            raise ValueError("MessageReciever not set up as queue")
        return self.queue.get(block=True)

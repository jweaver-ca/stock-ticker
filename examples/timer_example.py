# timer_example.py
#I want a time that repeats forever but can be paused (for rolling dice)
import threading
import time

def timer_func():
    print ("TIMER DONE!")

class MyTimer(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.paused = False
        self.restart_event = threading.Event()

    def run(self):
        while True:
            print ("Starting loop!")
            time.sleep(5)
            if self.paused:
                print (":( i was paused")
                self.restart_event.clear()
                self.restart_event.wait()
                self.paused = False
                print ("i woke up")
            else:
                print ("Ending loop1")

    def pause(self):
        self.paused = True

    def restart(self):
        if self.paused:
            self.paused = False
        if not self.restart_event.is_set():
            self.restart_event.set()
            
        
t = MyTimer()
t.start()

while True:
    ans = input('> ')
    if ans == 'c':
        t.pause()
    if ans == 'a':
        if t.paused:
            t.restart()
    

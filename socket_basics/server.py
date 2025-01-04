# from: https://stackoverflow.com/questions/7749341/basic-python-client-socket-example
# modified for python3

import socket

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.bind(('localhost', 8089))
serversocket.listen(5) # become a server socket, maximum 5 connections

while True:
    connection, address = serversocket.accept()
    buf = connection.recv(64)
    if len(buf) > 0:
        print (buf)
        # break <-- commented out, accepts many client connections, otherwise exits

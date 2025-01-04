# from: https://stackoverflow.com/questions/7749341/basic-python-client-socket-example
# modified for python3
# NOTE: client here does not read anything from server

import socket

clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientsocket.connect(('localhost', 8089))
clientsocket.send(bytes('hello', 'UTF-8'))

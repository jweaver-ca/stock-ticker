# stock-ticker
A Client/Server multiplayer version of the classic board game (that is mostly unheard of outside Canada!)

## About Stock Ticker
Players buy and sell stocks on a market that is constantly changing through die rolls made during game play. 
Buy your stocks and hope they go up, sell off the lame ducks, rake in cash from dividends, cry as they go down and ultimately
bust turning your shares into toilet paper!

## About this version
This online version was meant as an exercise in developing online games in python and is not meant to make
gamers swoon 'round the world.

## How to play
Clone the project.  Start the server with:

    $ python st_server.py
    
You'll have to edit it to run somewhere other than localhost.

Start a client with:

    $ python st_client.py --name EvilMrGetty --host localhost

The client program uses curses to draw the gameboard. Make sure your terminal window is
at least 80 chars wide before running.  Many features aren't implemented yet so don't cry when the countdown
doesn't work.

When all clients currently joined to the game press 'R' for ready, the game will begin and the stock market
will begin to move.

There is currently no end, so also there will be no winner unless someone loses all their money...

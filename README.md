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
    
You'll have to edit it to run somewhere other than `localhost`.

The client program uses curses to draw the gameboard. Windows users will very likely
have to install the curses library because it doesn't install on default python installs:

    $ pip install windows-curses

Start a client with:

    $ python st_client.py --name EvilMrGetty --host localhost

Make sure your terminal window is
at least 80 chars wide before running.  Many features aren't implemented yet so please don't 
cry when the countdown doesn't work.

When all clients currently joined to the game press `R` for ready, the game will begin 
and the stock market will begin to move.

A game is timed (current default is 15 minutes from start time).  When the end time has been
reached, the *next* die roll will bring on the game end.  The player with highest Net Worth (i.e.
cash and current value of portfolio) will be crowned the winner.  

You'll have to restart all the programs (currently) to play again.

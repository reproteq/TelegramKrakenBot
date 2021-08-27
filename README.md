# TelegramKrakenBot
---
## Python3 Telegram Bot For Trading in Kraken exchange

![alt tag](https://github.com/reproteq/TelegramKrakenBot/blob/main/TelegramKrakenBot.gif) 

---

> #### Functions:

1. Trading
2. Buy
3. Sell
4. Orders 
5. Balance
6. Alerts up price 
7. Alerts down price 
8. Alerts On/Off
9. Currency prices 
10. Funding 
11. Chart 
12. Updates

---
> #### Install
For install execute:

pip3 install -r requirements.txt


Install newest versions of needed modules

If you want to install the newest versions of the needed modules, execute the following:

pip3 install python-telegram-bot -U

pip3 install beautifulsoup4 -U

pip3 install krakenex -U

pip3 install requests -U

pip3 install jsonlines -U

For show all list of moduls installed in pip3 execute:

pip3 list


---
> #### Config

Edit files for configuration:

kraken.key

key 56 chars

key 88 chars




config.json

"user_id": "write here you telegram user_id"

"bot_token": "write here you telegram bot_token"


---
> #### Start

Starting

To start the bot execute:

python3 bot.py &



Starting

To start the bot but not close this when close shell execute:

nohup python3 bot.py &



Closing:

ps -ef | grep python3

kill id-process of python3 bot.py


---
> #### Tested

Tested versions

python3==3.8.10

krakenex==2.0.0

requests==2.18.4

beautifulsoup4==4.6.0

python-telegram-bot==13.7.0

jsonlines==2.0.0


---
> #### Info

Donations btc

1Mmwhdw4mQzbuLbmPFdEF2uXMVi8X3kv68

paypal 

reproteq@gmail.com

Special thanks Endogen

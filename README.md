<link rel="stylesheet" href="editormd/css/editormd.css" />
<div id="test-editor">
    <textarea style="display:none;">### Editor.md

**Editor.md**: The open source embeddable online markdown editor, based on CodeMirror & jQuery & Marked.
    </textarea>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/1.11.3/jquery.min.js"></script>
<script src="editormd/editormd.min.js"></script>
<script type="text/javascript">
    $(function() {
        var editor = editormd("test-editor", {
            // width  : "100%",
            // height : "100%",
            path   : "editormd/lib/"
        });
    });
</script>


# TelegramKrakenBot

Bot Telegram For Trading in Kraken exchange

Trading, buy, sell, orders, balance, alerts up price , alerts down price, currency prices, funding, chart, updates ...

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





Edit files for configuration:

kraken.key

key 56 chars

key 88 chars




config.json

"user_id": "write here you telegram user_id"

"bot_token": "write here you telegram bot_token"




Starting

To start the bot execute:

python3 bot.py &



Starting

To start the bot but not close this when close shell execute:

nohup python3 bot.py &



Closing:

ps -ef | grep python3

kill id-process of python3 bot.py




Tested versions

python3==3.8.10

krakenex==2.0.0

requests==2.18.4

beautifulsoup4==4.6.0

python-telegram-bot==13.7.0

jsonlines==2.0.0




![alt tag](https://github.com/reproteq/TelegramKrakenBot/blob/main/TelegramKrakenBot.gif) 





Donations btc

1Mmwhdw4mQzbuLbmPFdEF2uXMVi8X3kv68

paypal 

reproteq@gmail.com



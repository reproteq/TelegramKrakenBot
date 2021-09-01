#!/usr/bin/python3
import re,os,sys,json,time,inspect,logging,datetime, threading, requests, krakenex, telegram, jsonlines, urllib.request
from bs4 import BeautifulSoup
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode ,Update
from telegram.ext import Updater, CommandHandler, ConversationHandler, RegexHandler, MessageHandler, CallbackContext
from telegram.ext.filters import Filters
from emojis import *
from handlerclass import *

def main():
    print('Telegram Trade Bot v2.0 Kraken')
    return   

if os.path.isfile("config.json"):
    with open("config.json") as config_file:
        config = json.load(config_file)
else:
    exit("No configuration file 'config.json' found")

formatter_str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
date_format = "%y%m%d"
log_dir = "log"
logging.basicConfig(level=config["log_level"], format=formatter_str)
logger = logging.getLogger()
date = datetime.datetime.now().strftime(date_format)

if config["log_to_file"]:
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logfile_path = os.path.join(log_dir, date + ".log")
    handler = logging.FileHandler(logfile_path, encoding="utf-8")
    handler.setLevel(config["log_level"])
    formatter = logging.Formatter(formatter_str)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    sys.stderr = open(logfile_path, "w")

updater = Updater(token=config["bot_token"], use_context = True)
dispatcher = updater.dispatcher
job_queue = updater.job_queue

kraken = krakenex.API()
kraken.load_key("kraken.key")
trades = list()
orders = list()
assets = dict()
pairs = dict()
limits = dict()
alertas = list()
def log(severity, msg):
    if config["log_level"] == 0:
        return

    if config["log_to_file"]:
        now = datetime.datetime.now().strftime(date_format)

        if str(now) != str(date):
            for hdlr in logger.handlers[:]:
                logger.removeHandler(hdlr)

            new_hdlr = logging.FileHandler(logfile_path, encoding="utf-8")
            new_hdlr.setLevel(config["log_level"])
            new_hdlr.setFormatter(formatter)
            logger.addHandler(new_hdlr)
    logger.log(severity, msg)





def kraken_api(method, data=None, private=False, retries=None):
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    caller = inspect.currentframe().f_back.f_code.co_name
    log(logging.DEBUG, caller + " - args: " + str([(i, values[i]) for i in args]))

    try:
        if private:
            return kraken.query_private(method, data)
        else:
            return kraken.query_public(method, data)

    except Exception as ex:
        log(logging.ERROR, str(ex))
        ex_name = type(ex).__name__

        if "Incorrect padding" in str(ex):
            msg = "Incorrect padding: please verify that your Kraken API keys are valid"
            return {"error": [msg]}
        elif "Service:Unavailable" in str(ex):
            msg = "Service: Unavailable"
            return {"error": [msg]}
        if config["retries"] > 0:
            if retries is None:
                retries = config["retries"]
                return kraken_api(method, data, private, retries)
            elif retries > 0:
                retries -= 1
                return kraken_api(method, data, private, retries)
            else:
                return {"error": [ex_name + ":" + str(ex)]}
        else:
            return {"error": [ex_name + ":" + str(ex)]}


def restrict_access(func):
    def _restrict_access(update: Update, context: CallbackContext):
        chat_data = context.chat_data
        chat_id = get_chat_id(update)
        if str(chat_id) != config["user_id"]:
            if config["show_access_denied"]:
                updater.bot.send_message(chat_id, text="Access denied")
                msg = "Access denied for user %s" % chat_id
                updater.bot.send_message(config["user_id"], text=msg)

            log(logging.WARNING, msg)
            return
        else:
            return func(update, context)
    return _restrict_access


#todo balance con precio
@restrict_access
def balance_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving "+ e_sac + "balance..." )
    res_balance = kraken_api("Balance", private=True)
    if handle_api_error(res_balance, update):
        return
    res_orders = kraken_api("OpenOrders", private=True)

    if handle_api_error(res_orders, update):
        return

    msg = str()



    for currency_key, currency_value in res_balance["result"].items():
        available_value = currency_value

        # Go through all open orders and check if an order exists for the currency
        if res_orders["result"]["open"]:
            for order in res_orders["result"]["open"]:
                order_desc = res_orders["result"]["open"][order]["descr"]["order"]
                order_desc_list = order_desc.split(" ")

                order_type = order_desc_list[0]
                order_volume = order_desc_list[1]
                price_per_coin = order_desc_list[5]

                # Check if asset is fiat-currency (EUR, USD, ...) and BUY order
                #https://api.kraken.com/0/public/Assets
                #if currency_key.startswith("Z") and order_type == "buy":                
                #falla pq cardano no contiene z, buscar eur en el nombre
                
                if currency_key.startswith("Z") and order_type == "buy" :
                    available_value = float(available_value) - (float(order_volume) * float(price_per_coin))

                # Current asset is a coin and not a fiat currency
                else:
                    for asset, data in assets.items():
                        if order_desc_list[2].endswith(data["altname"]):
                            order_currency = order_desc_list[2][:-len(data["altname"])]
                            break

                    # Reduce current volume for coin if open sell-order exists
                    if assets[currency_key]["altname"] == order_currency and order_type == "sell":
                        available_value = float(available_value) - float(order_volume)

        # Only show assets with volume > 0
        if trim_zeros(currency_value) != "0":
            msg += bold(assets[currency_key]["altname"] + ": " + trim_zeros(currency_value) + "\n")
           
            '''
            #calc balance from last price            
            req_data = dict()
            req_data["pair"] = str()    
            # Add all configured asset pairs to the request
            for asset, trade_pair in pairs.items():
                req_data["pair"] += trade_pair + ","    
            req_data = {"pair": pairs[assets[currency_key]["altname"]]}            
            res_data = kraken_api("Ticker", data=req_data, private=False)                 
            last_trade_price = trim_zeros(res_data["result"][req_data["pair"]]["c"][0])

            
            for pair, data in res_data["result"].items():
                last_trade_price = trim_zeros(data["c"][0])
                coin = list(pairs.keys())[list(pairs.values()).index(pair)]
                   
            
            calc_price_currency = round((float(currency_value) *  float(last_trade_price)), 2)
            
            msg += bold("Price " + assets[currency_key]["altname"] + ": " +  last_trade_price + ' ' + config["used_pairs"][coin] + "\n")
            msg += bold("Balace" + ": " + str(calc_price_currency)  + ' ' +  config["used_pairs"][coin] + "\n")
            
            ###
            '''            
            available_value = trim_zeros(float(available_value))
            currency_value = trim_zeros(float(currency_value))

            # If orders exist for this asset, show available volume too
            if currency_value == available_value:
                msg += "(Available: all)\n"
            else:
                msg += "(Available: " + available_value + ")\n"

    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

######### ALERT
@restrict_access
def alert_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_ala + "Alerts System " + e_ntf)      
    reply_msg = "Selecct option ..."
    buttons = [
        KeyboardButton(KeyboardEnum.NEW_ALERT_DOWN.clean()),
        KeyboardButton(KeyboardEnum.NEW_ALERT_UP.clean()),        
        KeyboardButton(KeyboardEnum.REMOVE_ALL_ALERTS.clean()),
        KeyboardButton(KeyboardEnum.VIEW_ALL_ALERTS.clean())

    ]

    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.ALERT_NEW_REMOVE_ALL    

def alert_new_remove_all(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    clear_chat_data(chat_data)
    
    chat_data["alert"] = update.message.text.lower()
    reply_msg = "Choose currency"
    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    #new aler
    if chat_data["alert"].upper() == KeyboardEnum.NEW_ALERT.clean():
        cancel_btn.insert(0, KeyboardButton(KeyboardEnum.ALL_ALERT.clean()))
    #remove all alerts
    if chat_data["alert"].upper() == KeyboardEnum.REMOVE_ALL_ALERTS.clean():
        cancel_btn.insert(0, KeyboardButton(KeyboardEnum.REMOVE_ALL_ALERTS.clean()))
        #remove all lines file alerts.json
        file_path = "alerts.json"
        f = open(file_path, 'w')
        f.write('')
        f.close()
        #exit
        msg = e_ala + "Deleted alerts" + e_fns
        update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
        #return(update, context)


    #show all alerts
    if chat_data["alert"].upper() == KeyboardEnum.VIEW_ALL_ALERTS.clean():
        cancel_btn.insert(0, KeyboardButton(KeyboardEnum.VIEW_ALL_ALERTS.clean()))
        
        file_path = "alerts.json"  
        filesize = os.path.getsize(file_path) 
 
        if filesize != 0:        
            #loop alerts
            file_path = "alerts.json"       
            with open(file_path) as f:
               for line in f:
                   update.message.reply_text(e_ala + line)
                   
            update.message.reply_text("Show alls alerts")
            #return ConversationHandler.END
            return WorkflowEnum.ALERT_NEW_REMOVE_ALL
        
        else:
            update.message.reply_text("No alerts")
            #return ConversationHandler.END
            return WorkflowEnum.ALERT_NEW_REMOVE_ALL

        
    menu = build_menu(coin_buttons(), n_cols=3, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.ALERT_CURRENCY


def alert_currency(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    chat_data["currency"] = update.message.text.upper()
    asset_one, asset_two = assets_in_pair(pairs[chat_data["currency"]])
    chat_data["one"] = asset_one
    chat_data["two"] = asset_two
    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    reply_mrk = ReplyKeyboardMarkup(build_menu( cancel_btn), resize_keyboard=True)
    reply_msg = "Enter alert price coin in " + bold(assets[chat_data["two"]]["altname"])
    update.message.reply_text(reply_msg, reply_markup=reply_mrk, parse_mode=ParseMode.MARKDOWN)    
    return WorkflowEnum.ALERT_PRICE


def alert_price(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    reply_msg = chat_data  
    chat_data["price"] = update.message.text.upper().replace(",", ".")    
  
    buttons = [        
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]

    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)
    return WorkflowEnum.ALERT_CONFIRM



def alert_confirm(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    reply_msg = chat_data
    #save alerts to json file
    file_path = "alerts.json"
    with open(file_path, 'a') as file:
        #format reply_msg fomat to jsonlines
        jsonlstr = str(reply_msg).replace("'", '"')
        file.write(str(jsonlstr) +"\n") 

    buttons = [
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]  
    

    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    #clear_chat_data(chat_data)
    msg = e_ala + "Created alert" + e_fns
    update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

######### ALERTS
@restrict_access
def alerts_cmd(update: Update, context: CallbackContext):    
    update.message.reply_text(e_wit + "Retrieving alerts...")
    file_path = "alerts.json"  
    filesize = os.path.getsize(file_path) 
    # Reset global orders list
    global alerts_list
    alerts_list = list()  
    if filesize != 0: 
        file_path = "alerts.json"  
        with jsonlines.open(file_path) as f:
            for line in f.iter():
                linealert = line['alert']
                linecurrency = line['currency']
                lineprice = line['price']
                linealert_clean = linealert.replace('new alert','')
                alerts_list.append(linealert_clean +' '+ linecurrency + ' ' + lineprice )
                update.message.reply_text(bold(linealert_clean +' '+ linecurrency + ' ' + lineprice ), parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text(e_fns + bold("No open alerts"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    
    reply_msg = "What do you want to do?"

    buttons = [
        KeyboardButton(KeyboardEnum.CLOSE_ALERT.clean()),
        KeyboardButton(KeyboardEnum.CLOSE_ALL.clean())
    ]

    close_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(buttons, n_cols=2, footer_buttons=close_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)

    update.message.reply_text(reply_msg, reply_markup=reply_mrk)
     
    return WorkflowEnum.ALERTS_CLOSE 


def alerts_choose_alert(update: Update, context: CallbackContext):   

    buttons = list()
    # Go through all open orders and create a button
    if alerts_list:
        for alert in alerts_list:
            alert_id = next(iter(alert), None)
            buttons.append(KeyboardButton(alert))
    else:
        update.message.reply_text("No alerts")
        return ConversationHandler.END
        #return WorkflowEnum.ALERT_CLOSE_ALERT
    
    msg = "Which alert to close?"

    close_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(buttons, n_cols=1, footer_buttons=close_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)

    update.message.reply_text(msg, reply_markup=reply_mrk)
    return WorkflowEnum.ALERTS_CLOSE_ALERT


# Close the specified order
def alerts_close_alert(update: Update, context: CallbackContext): 
    update.message.reply_text(e_wit + "Closing alert..." )   
    req_data = update.message.text
    part_req_data = req_data.split(' ')
    al_tip = part_req_data[0]
    al_cur = part_req_data[1]
    al_pri = part_req_data[2]
    
    file_path = "alerts.json"  
    
    with jsonlines.open(file_path) as f:
        i=0
        for line in f.iter():
            i += 1
            li_al = line['alert']
            li_cur = line['currency']
            li_pri = line['price']
            li_alrp = li_al.replace('new alert ','')
           
            if ((li_alrp == al_tip) and (li_cur == al_cur) and (li_pri == al_pri)):
                filename = file_path
                line_to_delete = i
                initial_line = 1
                file_lines = {}
                
                with open(filename) as f:
                    content = f.readlines() 
                
                for line in content:
                    file_lines[initial_line] = line.strip()
                    initial_line += 1
                
                f = open(filename, "w")
                for line_number, line_content in file_lines.items():
                    if line_number != line_to_delete:
                        f.write('{}\n'.format(line_content))
                
                f.close()
                #print('Deleted line: {}'.format(line_to_delete))                
    
    msg = e_fns + bold("Alert closed " + req_data)
    update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


# Close all open orders
def alerts_close_all(update: Update, context: CallbackContext):

    update.message.reply_text(e_wit + "Closing all alerts ...")

    if alerts_list:
        file_path = "alerts.json"
        f = open(file_path, 'w')
        f.write('')
        f.close()
        
        msg = e_fns + bold("Alls alerts closed ")
        update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
    else:
        msg = e_fns + bold("No open alerts")
        update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END



###### Alerts in

@restrict_access
def alerton_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_ala + " ALERT YES/NO " + e_set)      
    reply_msg = "ALERT"
    buttons = [
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]  
    
    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)
    #return ConversationHandler.END
    return WorkflowEnum.ALERTON_CHEK
 
def alerton_chek(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    reply_msg = "ALERT"
    global alertsw
    #alerts on
    if update.message.text.upper() == KeyboardEnum.YES.clean():
        update.message.reply_text(e_ala + " ALERTS YES " + e_set)
        #alert switch on-off        
        alertsw = 'Restart' #thread alert control        

        
    #alerts off       
    if update.message.text.upper() == KeyboardEnum.NO.clean():
        update.message.reply_text(e_ala + " ALERT NO " + e_set)
        #alert switch on-off
        alertsw = 'Stop'  #thread alert control 
   
    
    buttons = [
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]  
    
    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    #clear_chat_data(chat_data)
    msg = e_ala + " ALERT CONFIG FINISHED " + e_fns
    update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


######trade
# Create orders to buy or sell currencies with price limit - choose 'buy' or 'sell'
@restrict_access
def trade_cmd(update: Update, context: CallbackContext):
    reply_msg = "Buy or sell?"

    buttons = [
        KeyboardButton(KeyboardEnum.BUY.clean()),
        KeyboardButton(KeyboardEnum.SELL.clean())
    ]

    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]

    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.TRADE_BUY_SELL

############buy sell
# Save if BUY or SELL order and choose the currency to trade
def trade_buy_sell(update: Update, context: CallbackContext):# chat_data):
    # Clear data in case command is executed again without properly exiting first
    chat_data = context.chat_data
    
    clear_chat_data(chat_data)

    chat_data["buysell"] = update.message.text.lower()

    reply_msg = "Choose currency"

    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]

    # If SELL chosen, then include button 'ALL' to sell everything
    if chat_data["buysell"].upper() == KeyboardEnum.SELL.clean():
        cancel_btn.insert(0, KeyboardButton(KeyboardEnum.ALL.clean()))

    menu = build_menu(coin_buttons(), n_cols=3, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.TRADE_CURRENCY


# Show confirmation to sell all assets
def trade_sell_all(update: Update, context: CallbackContext):
    msg = e_qst + "Sell " + bold("all") + " assets to current market price? All open orders will be closed!"
    update.message.reply_text(msg, reply_markup=keyboard_confirm(), parse_mode=ParseMode.MARKDOWN)

    return WorkflowEnum.TRADE_SELL_ALL_CONFIRM


# Sells all assets for there respective current market value
def trade_sell_all_confirm(update: Update, context: CallbackContext):
    if update.message.text.upper() == KeyboardEnum.NO.clean():
        return cancel(update, context)

    update.message.reply_text(e_wit + "Preparing to sell everything...")

    # Send request for open orders to Kraken
    res_open_orders = kraken_api("OpenOrders", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_open_orders, update):
        return

    # Close all currently open orders
    if res_open_orders["result"]["open"]:
        for order in res_open_orders["result"]["open"]:
            req_data = dict()
            req_data["txid"] = order

            # Send request to Kraken to cancel orders
            res_open_orders = kraken_api("CancelOrder", data=req_data, private=True)

            # If Kraken replied with an error, show it
            if handle_api_error(res_open_orders, update, "Not possible to close order\n" + order + "\n"):
                return

    # Send request to Kraken to get current balance of all assets
    res_balance = kraken_api("Balance", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_balance, update):
        return

    # Go over all assets and sell them
    for balance_asset, amount in res_balance["result"].items():
        # Asset is fiat-currency and not crypto-currency - skip it
        if balance_asset.startswith("Z"):
            continue

        # Filter out 0 volume currencies
        if amount == "0.0000000000":
            continue

        # Get clean asset name
        balance_asset = assets[balance_asset]["altname"]

        # Make sure that the order size is at least the minimum order limit
        if balance_asset in limits:
            if float(amount) < float(limits[balance_asset]):
                msg_error = e_err + "Volume to low. Must be > " + limits[balance_asset]
                msg_next = "Selling next asset..."

                update.message.reply_text(msg_error + "\n" + msg_next)
                log(logging.WARNING, msg_error)
                continue
        else:
            log(logging.WARNING, "No minimum order limit in config for coin " + balance_asset)
            continue

        req_data = dict()
        req_data["type"] = "sell"
        req_data["trading_agreement"] = "agree"
        req_data["pair"] = pairs[balance_asset]
        req_data["ordertype"] = "market"
        
       # req_data["volume"] = amount #ori
       
        #ttcode patch for fix EOrder: Insufficient funds
        fixVol = float(0.0000002) # fix EOrder: Insufficient funds
        chatVol = float(chat_data["volume"])    
        req_data["volume"] = str(chatVol - fixVol)   
        
        # Send request to create order to Kraken
        res_add_order = kraken_api("AddOrder", data=req_data, private=True)

        # If Kraken replied with an error, show it
        if handle_api_error(res_add_order, update):
            continue

    msg = e_fns + "Created orders to sell all assets"
    update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


# Save currency to trade and enter price per unit to trade
def trade_currency(update: Update, context: CallbackContext): 
    
    chat_data = context.chat_data
    chat_data["currency"] = update.message.text.upper()        
    #ttcode patch check len para ver si es nuevo formato       
    #balance_asset =  krakenPair(balance_asset)
        
    asset_one, asset_two = assets_in_pair(pairs[chat_data["currency"]])
    chat_data["one"] = asset_one
    chat_data["two"] = asset_two

    button = [KeyboardButton(KeyboardEnum.MARKET_PRICE.clean())]
    cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
    reply_mrk = ReplyKeyboardMarkup(build_menu(button, footer_buttons=cancel_btn), resize_keyboard=True)

    reply_msg = "Enter price per coin in " + bold(assets[chat_data["two"]]["altname"])
    update.message.reply_text(reply_msg, reply_markup=reply_mrk, parse_mode=ParseMode.MARKDOWN)
    return WorkflowEnum.TRADE_PRICE


# Save price per unit and choose how to enter the
# trade volume (fiat currency, volume or all available funds)
def trade_price(update: Update, context: CallbackContext):
    # Check if key 'market_price' already exists. Yes means that we
    # already saved the values and we only need to enter the volume again
    chat_data = context.chat_data
    if "market_price" not in chat_data:
        if update.message.text.upper() == KeyboardEnum.MARKET_PRICE.clean():
            chat_data["market_price"] = True
        else:
            chat_data["market_price"] = False
            chat_data["price"] = update.message.text.upper().replace(",", ".")

    reply_msg = "How to enter the volume?"

    # If price is 'MARKET PRICE' and it's a buy-order, don't show options
    # how to enter volume since there is only one way to do it
    if chat_data["market_price"] and chat_data["buysell"] == "buy":
        cancel_btn = build_menu([KeyboardButton(KeyboardEnum.CANCEL.clean())])
        reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)
        update.message.reply_text("Enter volume", reply_markup=reply_mrk)
        chat_data["vol_type"] = KeyboardEnum.VOLUME.clean()
        return WorkflowEnum.TRADE_VOLUME

    elif chat_data["market_price"] and chat_data["buysell"] == "sell":
        buttons = [
            KeyboardButton(KeyboardEnum.ALL.clean()),
            KeyboardButton(KeyboardEnum.VOLUME.clean())
        ]
        cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
        cancel_btn = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
        reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)

    else:
        buttons = [
            KeyboardButton(assets[chat_data["two"]]["altname"]),
            KeyboardButton(KeyboardEnum.VOLUME.clean()),
            KeyboardButton(KeyboardEnum.ALL.clean())
        ]
        cancel_btn = [KeyboardButton(KeyboardEnum.CANCEL.clean())]
        cancel_btn = build_menu(buttons, n_cols=3, footer_buttons=cancel_btn)
        reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)

    update.message.reply_text(reply_msg, reply_markup=reply_mrk)
    return WorkflowEnum.TRADE_VOL_TYPE


# Save volume type decision and enter volume
def trade_vol_asset(update: Update, context: CallbackContext):
    # Check if correct currency entered
    chat_data = context.chat_data
    if chat_data["two"].endswith(update.message.text.upper()):
        chat_data["vol_type"] = update.message.text.upper()
    else:
        update.message.reply_text(e_err + "Entered volume type not valid")
        return WorkflowEnum.TRADE_VOL_TYPE

    reply_msg = "Enter volume in " + bold(chat_data["vol_type"])

    cancel_btn = build_menu([KeyboardButton(KeyboardEnum.CANCEL.clean())])
    reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk, parse_mode=ParseMode.MARKDOWN)

    return WorkflowEnum.TRADE_VOLUME_ASSET


# Volume type 'VOLUME' chosen - meaning that
# you can enter the volume directly
def trade_vol_volume(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    chat_data["vol_type"] = update.message.text.upper()

    reply_msg = "Enter volume"

    cancel_btn = build_menu([KeyboardButton(KeyboardEnum.CANCEL.clean())])
    reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.TRADE_VOLUME

##### fee buy = (fee * Neur)/100 ##### feesell = (fee * (Nbtx* Eurpricebtx) / 100)
def FxFee(action, vol ,price):
    
    if action == "buy":        
        flofee = float(config["fee"])
        res = vol % flofee * 100
        resRound = round(res, 8)
        
    if action == "sell":
        flofee = float(config["fee"])
        res = (flofee * (vol * price)/ 100)
        resRound = round(res, 8)
        
    return resRound



# Volume type 'ALL' chosen - meaning that
# all available funds will be used
def trade_vol_all(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    #TODOTT
    #compruebaa formato si lleva xcoinzfiat si lo agrego para parchear funciones lo quitara si no lo dejara como  estaba, fix ada
    t = jsoncoin(chat_data["one"])
    chat_data["one"] = t

    update.message.reply_text(e_wit + "Calculating volume...")
    # Send request to Kraken to get current balance of all currencies
    res_balance = kraken_api("Balance", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_balance, update):
        return

    # Send request to Kraken to get open orders
    res_orders = kraken_api("OpenOrders", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_orders, update):
        return

    # BUY -----------------
    if chat_data["buysell"].upper() == KeyboardEnum.BUY.clean():
    
        # Get amount of available currency to buy from
        avail_buy_from_cur = float(res_balance["result"][chat_data["two"]])
          

        # Go through all open orders and check if buy-orders exist
        # If yes, subtract their value from the total of currency to buy from
        if res_orders["result"]["open"]:
            for order in res_orders["result"]["open"]:
                order_desc = res_orders["result"]["open"][order]["descr"]["order"]
                order_desc_list = order_desc.split(" ")
                coin_price = trim_zeros(order_desc_list[5])
                order_volume = order_desc_list[1]
                order_type = order_desc_list[0]

                if order_type == "buy":
                    avail_buy_from_cur = float(avail_buy_from_cur) - (float(order_volume) * float(coin_price))

        # Calculate volume depending on available trade-to balance and round it to 8 digits
        chat_data["volume"] = trim_zeros(avail_buy_from_cur / float(chat_data["price"]))

        # If available volume is 0, return without creating an order
        if chat_data["volume"] == "0.00000000":
            msg = e_err + "Available " + assets[chat_data["two"]]["altname"] + " volume is 0"
            update.message.reply_text(msg, reply_markup=keyboard_cmds())
            return ConversationHandler.END
        else:
            trade_show_conf(update,context)

    # SELL -----------------
    if chat_data["buysell"].upper() == KeyboardEnum.SELL.clean():
        
        available_volume = res_balance["result"][chat_data["one"]]        

        # Go through all open orders and check if sell-orders exists for the currency
        # If yes, subtract their volume from the available volume
        if res_orders["result"]["open"]:
            for order in res_orders["result"]["open"]:
                order_desc = res_orders["result"]["open"][order]["descr"]["order"]
                order_desc_list = order_desc.split(" ")

                # Get the currency of the order
                for asset, data in assets.items():
                    if order_desc_list[2].endswith(data["altname"]):
                        order_currency = order_desc_list[2][:-len(data["altname"])]
                        break

                order_volume = order_desc_list[1]
                order_type = order_desc_list[0]

                # Check if currency from oder is the same as currency to sell
                if chat_data["currency"] in order_currency:
                    if order_type == "sell":
                        available_volume = str(float(available_volume) - float(order_volume))
    

        # Get volume from balance and round it to 8 digits
        chat_data["volume"] = trim_zeros(float(available_volume))

        # If available volume is 0, return without creating an order
        if chat_data["volume"] == "0.00000000":
            msg = e_err + "Available " + chat_data["currency"] + " volume is 0"
            update.message.reply_text(msg, reply_markup=keyboard_cmds())
            return ConversationHandler.END
        else:
            trade_show_conf(update, context) 

    return WorkflowEnum.TRADE_CONFIRM


# Calculate the volume depending on entered volume type currency
def trade_volume_asset(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    amount = float(update.message.text.replace(",", "."))
    price_per_unit = float(chat_data["price"])
    chat_data["volume"] = trim_zeros(amount / price_per_unit)

    # Make sure that the order size is at least the minimum order limit
    if chat_data["currency"] in limits:
        if float(chat_data["volume"]) < float(limits[chat_data["currency"]]):
            msg_error = e_err + "Volume to low. Must be > " + limits[chat_data["currency"]]
            update.message.reply_text(msg_error)
            log(logging.WARNING, msg_error)

            reply_msg = "Enter new volume"
            cancel_btn = build_menu([KeyboardButton(KeyboardEnum.CANCEL.clean())])
            reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)
            update.message.reply_text(reply_msg, reply_markup=reply_mrk)

            return WorkflowEnum.TRADE_VOLUME
    else:
        log(logging.WARNING, "No minimum order limit in config for coin " + chat_data["currency"])

    trade_show_conf(update, context)

    return WorkflowEnum.TRADE_CONFIRM


# Calculate the volume depending on entered volume type 'VOLUME'
def trade_volume(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    chat_data["volume"] = trim_zeros(float(update.message.text.replace(",", ".")))

    # Make sure that the order size is at least the minimum order limit
    if chat_data["currency"] in limits:
        if float(chat_data["volume"]) < float(limits[chat_data["currency"]]):
            msg_error = e_err + "Volume to low. Must be > " + limits[chat_data["currency"]]
            update.message.reply_text(msg_error)
            log(logging.WARNING, msg_error)

            reply_msg = "Enter new volume"
            cancel_btn = build_menu([KeyboardButton(KeyboardEnum.CANCEL.clean())])
            reply_mrk = ReplyKeyboardMarkup(cancel_btn, resize_keyboard=True)
            update.message.reply_text(reply_msg, reply_markup=reply_mrk)

            return WorkflowEnum.TRADE_VOLUME
    else:
        log(logging.WARNING, "No minimum order limit in config for coin " + chat_data["currency"])

    trade_show_conf(update, context)

    return WorkflowEnum.TRADE_CONFIRM


# Calculate total value and show order description and confirmation for order creation
# This method is used in 'trade_volume' and in 'trade_vol_type_all'

def trade_show_conf(update: Update, context: CallbackContext):
#def trade_show_conf(update):
    chat_data = context.chat_data
    asset_two = assets[chat_data["two"]]["altname"]

    # Generate trade string to show at confirmation
    if chat_data["market_price"]:
        update.message.reply_text(e_wit + "Retrieving estimated price...")

        # Send request to Kraken to get current trading price for pair
        res_data = kraken_api("Ticker", data={"pair": pairs[chat_data["currency"]]}, private=False)

        # If Kraken replied with an error, show it
        if handle_api_error(res_data, update):
            return

        chat_data["price"] = res_data["result"][pairs[chat_data["currency"]]]["c"][0]

        chat_data["trade_str"] = (chat_data["buysell"].lower() + " " +
                                  trim_zeros(chat_data["volume"]) + " " +
                                  chat_data["currency"] + " @ market price ≈" +
                                  trim_zeros(chat_data["price"]) + " " +
                                  asset_two)
        
        #fxfee calculate buysell  market price
        action = chat_data["buysell"]
        vol = chat_data["volume"]
        price = chat_data["price"]
        nfee = FxFee(action, float(vol), float(price))
        flofee = float(nfee)
        strfee = str(round(nfee, 2))        
        strconfee = str(float(config["fee"]))
        update.message.reply_text(e_wit + "Fee " + strconfee + "% " + strfee +" " + asset_two)

    else:
        chat_data["trade_str"] = (chat_data["buysell"].lower() + " " +
                                  trim_zeros(chat_data["volume"]) + " " +
                                  chat_data["currency"] + " @ limit " +
                                  trim_zeros(chat_data["price"]) + " " +
                                  asset_two)
      
        #fxfee calculate buysell price tiped
        action = chat_data["buysell"]
        vol = chat_data["volume"]
        price = chat_data["price"]
        nfee = FxFee(action, float(vol), float(price))
        flofee = float(nfee)
        strfee = str(round(nfee, 2))
        strconfee = str(float(config["fee"]))
        update.message.reply_text(e_wit + "Fee " + strconfee + "% " + strfee +" " + asset_two)



    # If fiat currency, then show 2 digits after decimal place
    if chat_data["two"].startswith("Z"):
        # Calculate total value of order
        total_value = trim_zeros(float(chat_data["volume"]) * float(chat_data["price"]), 2)
        #total_value = trim_zeros(float(rnewvol) * float(chat_data["price"]), 2) 
    # Else, show 8 digits after decimal place
    else:
        # Calculate total value of order
        total_value = trim_zeros(float(chat_data["volume"]) * float(chat_data["price"])) 
        #total_value = trim_zeros(float(rnewvol)  * float(chat_data["price"]))
        
    if chat_data["market_price"]:
        total_value_str = "(Value: ≈" + str(trim_zeros(total_value)) + " " + asset_two + ")"
    else:
        total_value_str = "(Value: " + str(trim_zeros(total_value)) + " " + asset_two + ")"

   # update.message.reply_text(e_wit + "FloFeestr " + str(flofee) +" " + asset_two)

    msg = e_qst + "Place this order?\n" + chat_data["trade_str"] + "\n" + total_value_str
    update.message.reply_text(msg, reply_markup=keyboard_confirm())


# The user has to confirm placing the order
def trade_confirm(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    if update.message.text.upper() == KeyboardEnum.NO.clean():
        return cancel(update, context, chat_data=chat_data)

    update.message.reply_text(e_wit + "Placing order...")

    req_data = dict()
    req_data["type"] = chat_data["buysell"].lower()
    
    #ttcode patch for fix EOrder: Insufficient funds
    fixVol = float(0.0000002) # fix EOrder: Insufficient funds
    chatVol = float(chat_data["volume"])    
    req_data["volume"] = str(chatVol - fixVol)     
    
    #req_data["volume"] = chat_data["volume"]#ori
    req_data["pair"] = pairs[chat_data["currency"]]

    # Order type MARKET
    if chat_data["market_price"]:
        req_data["ordertype"] = "market"
        req_data["trading_agreement"] = "agree"

    # Order type LIMIT
    else:
        req_data["ordertype"] = "limit"
        req_data["price"] = chat_data["price"]

    # Send request to create order to Kraken
    res_add_order = kraken_api("AddOrder", req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_add_order, update):
        return

    # If there is a transaction ID then the order was placed successfully
    if res_add_order["result"]["txid"]:
        msg = e_fns + "Order placed:\n" + res_add_order["result"]["txid"][0] + "\n" + chat_data["trade_str"]
        update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text("Undefined state: no error and no TXID")

    clear_chat_data(chat_data)
    return ConversationHandler.END


# Show and manage orders
@restrict_access
def orders_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving orders...")

    # Send request to Kraken to get open orders
    res_data = kraken_api("OpenOrders", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_data, update):
        return

    # Reset global orders list
    global orders
    orders = list()

    # Go through all open orders and show them to the user
    if res_data["result"]["open"]:
        for order_id, order_details in res_data["result"]["open"].items():
            # Add order to global order list so that it can be used later
            # without requesting data from Kraken again
            orders.append({order_id: order_details})

            order = "Order: " + order_id
            order_desc = trim_zeros(order_details["descr"]["order"])
            update.message.reply_text(bold(order + "\n" + order_desc), parse_mode=ParseMode.MARKDOWN)
    else:
        update.message.reply_text(e_fns + bold("No open orders"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    reply_msg = "What do you want to do?"

    buttons = [
        KeyboardButton(KeyboardEnum.CLOSE_ORDER.clean()),
        KeyboardButton(KeyboardEnum.CLOSE_ALL.clean())
    ]

    close_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(buttons, n_cols=2, footer_buttons=close_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)

    update.message.reply_text(reply_msg, reply_markup=reply_mrk)
    return WorkflowEnum.ORDERS_CLOSE


# Choose what to do with the open orders
def orders_choose_order(update: Update, context: CallbackContext):
    buttons = list()

    # Go through all open orders and create a button
    if orders:
        for order in orders:
            order_id = next(iter(order), None)
            buttons.append(KeyboardButton(order_id))
    else:
        update.message.reply_text("No open orders")
        return ConversationHandler.END

    msg = "Which order to close?"

    close_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(buttons, n_cols=1, footer_buttons=close_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)

    update.message.reply_text(msg, reply_markup=reply_mrk)
    return WorkflowEnum.ORDERS_CLOSE_ORDER


# Close all open orders
def orders_close_all(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Closing orders...")

    closed_orders = list()

    if orders:
        for x in range(0, len(orders)):
            order_id = next(iter(orders[x]), None)

            # Send request to Kraken to cancel orders
            res_data = kraken_api("CancelOrder", data={"txid": order_id}, private=True)

            # If Kraken replied with an error, show it
            if handle_api_error(res_data, update, "Order not closed:\n" + order_id + "\n"):
                # If we are currently not closing the last order,
                # show message that we a continuing with the next one
                if x+1 != len(orders):
                    update.message.reply_text(e_wit + "Closing next order...")
            else:
                closed_orders.append(order_id)

        if closed_orders:
            msg = e_fns + bold("Orders closed:\n" + "\n".join(closed_orders))
            update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
        else:
            msg = e_fns + bold("No orders closed")
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return
    else:
        msg = e_fns + bold("No open orders")
        update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


# Close the specified order
def orders_close_order(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Closing order...")

    req_data = dict()
    req_data["txid"] = update.message.text

    # Send request to Kraken to cancel order
    res_data = kraken_api("CancelOrder", data=req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_data, update):
        return

    msg = e_fns + bold("Order closed:\n" + req_data["txid"])
    update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


# Show the last trade price for a currency
@restrict_access
def price_cmd(update: Update, context: CallbackContext):
    # If single-price option is active, get prices for all coins
    if config["single_price"]:
        update.message.reply_text(e_wit + "Retrieving prices...")

        req_data = dict()
        req_data["pair"] = str()

        # Add all configured asset pairs to the request
        for asset, trade_pair in pairs.items():
            req_data["pair"] += trade_pair + ","

        # Get rid of last comma
        req_data["pair"] = req_data["pair"][:-1]

        # Send request to Kraken to get current trading price for currency-pair
        res_data = kraken_api("Ticker", data=req_data, private=False)

        # If Kraken replied with an error, show it
        if handle_api_error(res_data, update):
            return

        msg = str()

        for pair, data in res_data["result"].items():
            last_trade_price = trim_zeros(data["c"][0])
            coin = list(pairs.keys())[list(pairs.values()).index(pair)]
            msg += coin + ": " + last_trade_price + " " + config["used_pairs"][coin] + "\n"

        update.message.reply_text(bold(msg), parse_mode=ParseMode.MARKDOWN)

        return ConversationHandler.END

    # Let user choose for which coin to get the price
    else:
        reply_msg = "Choose currency"

        cancel_btn = [
            KeyboardButton(KeyboardEnum.CANCEL.clean())
        ]

        menu = build_menu(coin_buttons(), n_cols=3, footer_buttons=cancel_btn)
        reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
        update.message.reply_text(reply_msg, reply_markup=reply_mrk)

        return WorkflowEnum.PRICE_CURRENCY


# Choose for which currency to show the last trade price
def price_currency(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving price...")

    currency = update.message.text.upper()
    req_data = {"pair": pairs[currency]}

    # Send request to Kraken to get current trading price for currency-pair
    res_data = kraken_api("Ticker", data=req_data, private=False)

    # If Kraken replied with an error, show it
    if handle_api_error(res_data, update):
        return

    last_trade_price = trim_zeros(res_data["result"][req_data["pair"]]["c"][0])

    msg = bold(currency + ": " + last_trade_price + " " + config["used_pairs"][currency])
    update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


# Show the current real money value for a certain asset or for all assets combined
@restrict_access
def value_cmd(update: Update, context: CallbackContext):
    reply_msg = "Choose currency"

    footer_btns = [
        KeyboardButton(KeyboardEnum.ALL.clean()),
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(coin_buttons(), n_cols=3, footer_buttons=footer_btns)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.VALUE_CURRENCY


# Choose for which currency you want to know the current value
def value_currency(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving current value...")

    # ALL COINS (balance of all coins)
    if update.message.text.upper() == KeyboardEnum.ALL.clean():
        req_asset = dict()
        req_asset["asset"] = config["base_currency"]

        # Send request to Kraken tp obtain the combined balance of all currencies
        res_trade_balance = kraken_api("TradeBalance", data=req_asset, private=True)

        # If Kraken replied with an error, show it
        if handle_api_error(res_trade_balance, update):
            return


        for asset, data in assets.items():
            if data["altname"] == config["base_currency"]:
                if asset.startswith("Z"):
                    # It's a fiat currency, show only 2 digits after decimal place
                    total_fiat_value = trim_zeros(float(res_trade_balance["result"]["eb"]), 2)
                else:
                    # It's not a fiat currency, show 8 digits after decimal place
                    total_fiat_value = trim_zeros(float(res_trade_balance["result"]["eb"]))

        # Generate message to user
        msg = e_fns + bold("Overall: " + total_fiat_value + " " + config["base_currency"])
        update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    # ONE COINS (balance of specific coin)
    else:
        # Send request to Kraken to get balance of all currencies
        res_balance = kraken_api("Balance", private=True)

        # If Kraken replied with an error, show it
        if handle_api_error(res_balance, update):
            return

        req_price = dict()
        
        # Get pair string for chosen currency
        req_price["pair"] = pairs[update.message.text.upper()]

        # Send request to Kraken to get current trading price for currency-pair
        res_price = kraken_api("Ticker", data=req_price, private=False)

        # If Kraken replied with an error, show it
        if handle_api_error(res_price, update):
            return

        # Get last trade price
        pair = list(res_price["result"].keys())[0]
        last_price = res_price["result"][pair]["c"][0]
        
        #fix issue ada
        #asset = assets_in_pair(pair)

        value = float(0)

        for asset, data in assets.items():
            if data["altname"] == update.message.text.upper():
                # if is format 8len same XXBTZEUR
                if len(pair) == 8:
                    buy_from_cur_long = pair.replace(asset, "")
                    buy_from_cur = assets[buy_from_cur_long]["altname"]
                    # Calculate value by multiplying balance with last trade price
                    value = float(res_balance["result"][asset]) * float(last_price)
                    break
                else:                 
                    # Calculate value by multiplying balance with last trade price
                    value = float(res_balance["result"][asset]) * float(last_price)
                    break
        '''
        # If fiat currency, show 2 digits after decimal place
        if buy_from_cur_long.startswith("Z"):
            value = trim_zeros(value, 2)
            last_trade_price = trim_zeros(float(last_price), 2)
        # ... else show 8 digits after decimal place
        else:
            value = trim_zeros(value)
            last_trade_price = trim_zeros(float(last_price))
            
        msg = update.message.text.upper() + ": " + value + " " + buy_from_cur    
        '''
        value = trim_zeros(value, 2)
        last_trade_price = trim_zeros(float(last_price),2)
        msg = update.message.text.upper() + ": " + str(value) 

        # Add last trade price to msg
        #msg += "\n(Ticker: " + last_trade_price + " " + buy_from_cur + ")"
        msg += "\n(Ticker: " + str(last_trade_price) +  ")"
        
        update.message.reply_text(bold(msg), reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


# Reloads keyboard with available commands
@restrict_access
def reload_cmd(update: Update, context: CallbackContext):
    msg = e_wit + "Reloading keyboard..."
    update.message.reply_text(msg, reply_markup=keyboard_cmds())
    return ConversationHandler.END


# Get current state of Kraken API
# Is it under maintenance or functional?
@restrict_access
def state_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving API state...")

    msg = "Kraken API Status: " + bold(api_state()) + "\nhttps://status.kraken.com"
    updater.bot.send_message(config["user_id"],
                             msg,
                             reply_markup=keyboard_cmds(),
                             disable_web_page_preview=True,
                             parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


def start_cmd(update: Update, context: CallbackContext):
    msg = e_bgn + "Welcome to Kraken-Telegram-Bot by TT 2021!"
    update.message.reply_text(msg, reply_markup=keyboard_cmds())


# Returns a string representation of a trade. Looks like this:
# sell 0.03752345 ETH-EUR @ limit 267.5 on 2017-08-22 22:18:22
def get_trade_str(trade):
    from_asset, to_asset = assets_in_pair(trade["pair"])

    if from_asset and to_asset:
        # Build string representation of trade with asset names
        trade_str = (trade["type"] + " " +
                     trim_zeros(trade["vol"]) + " " +
                     assets[from_asset]["altname"] + " @ " +
                     trim_zeros(trade["price"]) + " " +
                     assets[to_asset]["altname"] + "\n" +
                     datetime_from_timestamp(trade["time"]))
    else:
        # Build string representation of trade with pair string
        # We need this because who knows if the pair still exists
        trade_str = (trade["type"] + " " +
                     trim_zeros(trade["vol"]) + " " +
                     trade["pair"] + " @ " +
                     trim_zeros(trade["price"]) + "\n" +
                     datetime_from_timestamp(trade["time"]))

    return trade_str


# Shows executed trades with volume and price
@restrict_access
def trades_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_wit + "Retrieving executed trades...")

    # Send request to Kraken to get trades history
    res_trades = kraken_api("TradesHistory", private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_trades, update):
        return

    # Reset global trades list
    global trades
    trades = list()

    # Add all trades to global list
    for trade_id, trade_details in res_trades["result"]["trades"].items():
        trades.append(trade_details)

    if trades:
        # Sort global list with trades - on executed time
        trades = sorted(trades, key=lambda k: k['time'], reverse=True)

        buttons = [
            KeyboardButton(KeyboardEnum.NEXT.clean()),
            KeyboardButton(KeyboardEnum.CANCEL.clean())
        ]

        # Get number of first items in list (latest trades)
        for items in range(config["history_items"]):
            newest_trade = next(iter(trades), None)

            _, two = assets_in_pair(newest_trade["pair"])

            # It's a fiat currency
            if two.startswith("Z"):
                total_value = trim_zeros(float(newest_trade["cost"]), 2)
            # It's a digital currency
            else:
                total_value = trim_zeros(float(newest_trade["cost"]))

            reply_mrk = ReplyKeyboardMarkup(build_menu(buttons, n_cols=2), resize_keyboard=True)
            msg = get_trade_str(newest_trade) + " (Value: " + total_value + " " + assets[two]["altname"] + ")"
            update.message.reply_text(bold(msg), reply_markup=reply_mrk, parse_mode=ParseMode.MARKDOWN)

            # Remove the first item in the trades list
            trades.remove(newest_trade)

        return WorkflowEnum.TRADES_NEXT
    else:
        update.message.reply_text("No item in trade history", reply_markup=keyboard_cmds())

        return ConversationHandler.END


# TODO: Show fee
# Save if BUY, SELL or ALL trade history and choose how many entries to list
def trades_next(update: Update, context: CallbackContext):
    if trades:
        # Get number of first items in list (latest trades)
        for items in range(config["history_items"]):
            newest_trade = next(iter(trades), None)

            one, two = assets_in_pair(newest_trade["pair"])

            # It's a fiat currency
            if two.startswith("Z"):
                total_value = trim_zeros(float(newest_trade["cost"]), 2)
            # It's a digital currency
            else:
                total_value = trim_zeros(float(newest_trade["cost"]))

            msg = get_trade_str(newest_trade) + " (Value: " + total_value + " " + assets[two]["altname"] + ")"
            update.message.reply_text(bold(msg), parse_mode=ParseMode.MARKDOWN)

            # Remove the first item in the trades list
            trades.remove(newest_trade)

        return WorkflowEnum.TRADES_NEXT
    else:
        msg = e_fns + bold("Trade history is empty")
        update.message.reply_text(msg, reply_markup=keyboard_cmds(), parse_mode=ParseMode.MARKDOWN)

        return ConversationHandler.END


# Shows sub-commands to control the bot
@restrict_access
def bot_cmd(update: Update, context: CallbackContext):
    reply_msg = "What do you want to do?"

    buttons = [
        KeyboardButton(KeyboardEnum.UPDATE_CHECK.clean()),
        KeyboardButton(KeyboardEnum.UPDATE.clean()),
        KeyboardButton(KeyboardEnum.RESTART.clean()),
        KeyboardButton(KeyboardEnum.SHUTDOWN.clean()),
        KeyboardButton(KeyboardEnum.SETTINGS.clean()),
        KeyboardButton(KeyboardEnum.API_STATE.clean()),
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    reply_mrk = ReplyKeyboardMarkup(build_menu(buttons, n_cols=2), resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.BOT_SUB_CMD


# Execute chosen sub-cmd of 'bot' cmd
def bot_sub_cmd(update: Update, context: CallbackContext):
    # Update check
    if update.message.text.upper() == KeyboardEnum.UPDATE_CHECK.clean():
        status_code, msg = get_update_state()
        update.message.reply_text(msg)
        return

    # Update
    elif update.message.text.upper() == KeyboardEnum.UPDATE.clean():
        return update_cmd(update, context)

    # Restart
    elif update.message.text.upper() == KeyboardEnum.RESTART.clean():
        restart_cmd(update, context)

    # Shutdown
    elif update.message.text.upper() == KeyboardEnum.SHUTDOWN.clean():
        shutdown_cmd(update, context)

    # API State
    elif update.message.text.upper() == KeyboardEnum.API_STATE.clean():
        state_cmd(update, context)

    # Cancel
    elif update.message.text.upper() == KeyboardEnum.CANCEL.clean():
        return cancel(update, context)

# Show links to Kraken currency charts
@restrict_access
def chart_cmd(update, context):
    # Send only one message with all configured charts
    if config["single_chart"]:
        msg = str()

        for coin, url in config["coin_charts"].items():
            msg += coin + ": " + url + "\n"

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard_cmds())

        return ConversationHandler.END

    # Choose currency and display chart for it
    else:
        reply_msg = "Choose currency"

        buttons = list()
        for coin, url in config["coin_charts"].items():
            buttons.append(KeyboardButton(coin))

        cancel_btn = [
            KeyboardButton(KeyboardEnum.CANCEL.clean())
        ]

        menu = build_menu(buttons, n_cols=3, footer_buttons=cancel_btn)
        reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
        update.message.reply_text(reply_msg, reply_markup=reply_mrk)

        return WorkflowEnum.CHART_CURRENCY


# Get chart URL for every coin in config
def chart_currency(update: Update, context: CallbackContext):
    currency = update.message.text

    for coin, url in config["coin_charts"].items():
        if currency.upper() == coin.upper():
            update.message.reply_text(url, reply_markup=keyboard_cmds())
            break

    return ConversationHandler.END


# Choose currency to deposit or withdraw funds to / from
@restrict_access
def funding_cmd(update: Update, context: CallbackContext):
    reply_msg = "Choose currency"

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(coin_buttons(), n_cols=3, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.FUNDING_CURRENCY


# Choose withdraw or deposit
def funding_currency(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    # Clear data in case command is executed again without properly exiting first
    clear_chat_data(chat_data)

    chat_data["currency"] = update.message.text.upper()

    reply_msg = "What do you want to do?"

    buttons = [
        KeyboardButton(KeyboardEnum.DEPOSIT.clean()),
        KeyboardButton(KeyboardEnum.WITHDRAW.clean())
    ]

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.FUNDING_CHOOSE


# Get wallet addresses to deposit to
def funding_deposit(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    update.message.reply_text(e_wit + "Retrieving wallets to deposit...")

    req_data = dict()
    req_data["asset"] = chat_data["currency"]

    # Send request to Kraken to get trades history
    res_dep_meth = kraken_api("DepositMethods", data=req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_dep_meth, update):
        return

    req_data["method"] = res_dep_meth["result"][0]["method"]

    # Send request to Kraken to get trades history
    res_dep_addr = kraken_api("DepositAddresses", data=req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_dep_addr, update):
        return

    # Wallet found
    if res_dep_addr["result"]:
        for wallet in res_dep_addr["result"]:
            expire_info = datetime_from_timestamp(wallet["expiretm"]) if wallet["expiretm"] != "0" else "No"
            msg = wallet["address"] + "\nExpire: " + expire_info
            update.message.reply_text(bold(msg), parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard_cmds())
    # No wallet found
    else:
        update.message.reply_text("No wallet found", reply_markup=keyboard_cmds())

    return ConversationHandler.END


def funding_withdraw(update: Update, context: CallbackContext):
    update.message.reply_text("Enter target wallet name", reply_markup=ReplyKeyboardRemove())

    return WorkflowEnum.WITHDRAW_WALLET


def funding_withdraw_wallet(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    chat_data["wallet"] = update.message.text

    update.message.reply_text("Enter " + chat_data["currency"] + " volume to withdraw")

    return WorkflowEnum.WITHDRAW_VOLUME


def funding_withdraw_volume(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    chat_data["volume"] = update.message.text.replace(",", ".")

    volume = chat_data["volume"]
    currency = chat_data["currency"]
    wallet = chat_data["wallet"]
    msg = e_qst + "Withdraw " + volume + " " + currency + " to wallet " + wallet + "?"

    update.message.reply_text(msg, reply_markup=keyboard_confirm())

    return WorkflowEnum.WITHDRAW_CONFIRM


# Withdraw funds from wallet
def funding_withdraw_confirm(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    if update.message.text.upper() == KeyboardEnum.NO.clean():
        return cancel(update, context, chat_data=chat_data)

    update.message.reply_text(e_wit + "Withdrawal initiated...")

    req_data = dict()
    req_data["asset"] = chat_data["currency"]
    req_data["key"] = chat_data["wallet"]
    req_data["amount"] = chat_data["volume"]

    # Send request to Kraken to get withdrawal info to lookup fee
    res_data = kraken_api("WithdrawInfo", data=req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_data, update):
        return

    # Add up volume and fee and set the new value as 'amount'
    volume_and_fee = float(req_data["amount"]) + float(res_data["result"]["fee"])
    req_data["amount"] = str(volume_and_fee)

    # Send request to Kraken to withdraw digital currency
    res_data = kraken_api("Withdraw", data=req_data, private=True)

    # If Kraken replied with an error, show it
    if handle_api_error(res_data, update):
        return

    # If a REFID exists, the withdrawal was initiated
    if res_data["result"]["refid"]:
        msg = e_fns + "Withdrawal executed\nREFID: " + res_data["result"]["refid"]
        update.message.reply_text(msg)
    else:
        msg = e_err + "Undefined state: no error and no REFID"
        update.message.reply_text(msg)

    clear_chat_data(chat_data)
    return ConversationHandler.END


# Download newest script, update the currently running one and restart.
# If 'config.json' changed, update it also
@restrict_access
def update_cmd(update: Update, context: CallbackContext):
    # Get newest version of this script from GitHub
    headers = {"If-None-Match": config["update_hash"]}
    github_script = requests.get(config["update_url"], headers=headers)

    # Status code 304 = Not Modified
    if github_script.status_code == 304:
        msg = "You are running the latest version"
        update.message.reply_text(msg, reply_markup=keyboard_cmds())
    # Status code 200 = OK
    elif github_script.status_code == 200:
        # Get github 'config.json' file
        last_slash_index = config["update_url"].rfind("/")
        github_config_path = config["update_url"][:last_slash_index + 1] + "config.json"
        github_config_file = requests.get(github_config_path)
        github_config = json.loads(github_config_file.text)

        # Compare current config keys with
        # config keys from github-config
        if set(config) != set(github_config):
            # Go through all keys in github-config and
            # if they are not present in current config, add them
            for key, value in github_config.items():
                if key not in config:
                    config[key] = value

        # Save current ETag (hash) of bot script in github-config
        e_tag = github_script.headers.get("ETag")
        config["update_hash"] = e_tag

        # Save changed github-config as new config
        with open("config.json", "w") as cfg:
            json.dump(config, cfg, indent=4)

        # Get the name of the currently running script
        path_split = os.path.split(str(sys.argv[0]))
        filename = path_split[len(path_split)-1]

        # Save the content of the remote file
        with open(filename, "w") as file:
            file.write(github_script.text)

        # Restart the bot
        restart_cmd(update, context)

    # Every other status code
    else:
        msg = e_err + "Update not executed. Unexpected status code: " + github_script.status_code
        update.message.reply_text(msg, reply_markup=keyboard_cmds())

    return ConversationHandler.END


# This needs to be run on a new thread because calling 'updater.stop()' inside a
# handler (shutdown_cmd) causes a deadlock because it waits for itself to finish
def shutdown():
    updater.stop()
    updater.is_idle = False


# Terminate this script
@restrict_access
def shutdown_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(e_gby + "Shutting down...", reply_markup=ReplyKeyboardRemove())

    # See comments on the 'shutdown' function
    threading.Thread(target=shutdown).start()


# Restart this python script
@restrict_access
def restart_cmd(update: Update, context: CallbackContext):
    msg = e_wit + "Bot is restarting..."
    update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

    time.sleep(0.2)
    os.execl(sys.executable, sys.executable, *sys.argv)


# Get current settings
@restrict_access
def settings_cmd(update: Update, context: CallbackContext):
    settings = str()
    buttons = list()

    # Go through all settings in config file
    for key, value in config.items():
        settings += key + " = " + str(value) + "\n\n"
        buttons.append(KeyboardButton(key.upper()))

    # Send message with all current settings (key & value)
    update.message.reply_text(settings)

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    msg = "Choose key to change value"

    menu = build_menu(buttons, n_cols=2, footer_buttons=cancel_btn)
    reply_mrk = ReplyKeyboardMarkup(menu, resize_keyboard=True)
    update.message.reply_text(msg, reply_markup=reply_mrk)

    return WorkflowEnum.SETTINGS_CHANGE


# Change setting
def settings_change(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    # Clear data in case command is executed again without properly exiting first
    clear_chat_data(chat_data)

    chat_data["setting"] = update.message.text.lower()

    # Don't allow to change setting 'user_id'
    if update.message.text.upper() == "USER_ID":
        update.message.reply_text("It's not possible to change USER_ID value")
        return

    msg = "Enter new value"

    update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

    return WorkflowEnum.SETTINGS_SAVE


# Save new value for chosen setting
def settings_save(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    new_value = update.message.text

    # Check if new value is a boolean
    if new_value.lower() == "true":
        chat_data["value"] = True
    elif new_value.lower() == "false":
        chat_data["value"] = False
    else:
        # Check if new value is an integer ...
        try:
            chat_data["value"] = int(new_value)
        # ... if not, save as string
        except ValueError:
            chat_data["value"] = new_value

    msg = e_qst + "Save new value and restart bot?"
    update.message.reply_text(msg, reply_markup=keyboard_confirm())

    return WorkflowEnum.SETTINGS_CONFIRM


# Confirm saving new setting and restart bot
def settings_confirm(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    if update.message.text.upper() == KeyboardEnum.NO.clean():
        return cancel(update, context, chat_data=chat_data)

    # Set new value in config dictionary
    config[chat_data["setting"]] = chat_data["value"]

    # Save changed config as new one
    with open("config.json", "w") as cfg:
        json.dump(config, cfg, indent=4)

    update.message.reply_text(e_fns + "New value saved")

    # Restart bot to activate new setting
    restart_cmd(update, context)


# Remove all data from 'chat_data' since we are canceling / ending
# the conversation. If this is not done, next conversation will
# have all the old values
def clear_chat_data(chat_data):
    if chat_data:
        for key in list(chat_data.keys()):
            del chat_data[key]


# Will show a cancel message, end the conversation and show the default keyboard
def cancel(update: Update, context: CallbackContext, chat_data=None):
    # Clear 'chat_data' for next conversation
    clear_chat_data(chat_data)

    # Show the commands keyboard and end the current conversation
    update.message.reply_text(e_cnc + "Canceled...", reply_markup=keyboard_cmds())
    return ConversationHandler.END


# Check if GitHub hosts a different script then the currently running one
def get_update_state():
    # Get newest version of this script from GitHub
    headers = {"If-None-Match": config["update_hash"]}
    github_file = requests.get(config["update_url"], headers=headers)

    # Status code 304 = Not Modified (remote file has same hash, is the same version)
    if github_file.status_code == 304:
        msg = e_top + "Bot is up to date"
    # Status code 200 = OK (remote file has different hash, is not the same version)
    elif github_file.status_code == 200:
        msg = e_ntf + "New version available. Get it with /update"
    # Every other status code
    else:
        msg = e_err + "Update check not possible. Unexpected status code: " + github_file.status_code

    return github_file.status_code, msg


# Return chat ID for an update object
def get_chat_id(update=None):
    if update:
        if update.message:
            return update.message.chat_id
        elif update.callback_query:
            return update.callback_query.from_user["id"]
    else:
        return config["user_id"]


# Create a button menu to show in Telegram messages
def build_menu(buttons, n_cols=1, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)

    return menu


# Custom keyboard that shows all available commands
def keyboard_cmds():
    command_buttons = [
        KeyboardButton("/trade"),
        KeyboardButton("/orders"),
        KeyboardButton("/balance"),
        KeyboardButton("/price"),
        KeyboardButton("/value"),
        KeyboardButton("/chart"),
        KeyboardButton("/trades"),
        KeyboardButton("/funding"),
        KeyboardButton("/bot"),
        KeyboardButton("/alerts"),
        KeyboardButton("/alert"),
        KeyboardButton("/alertOn")      
    ]

    return ReplyKeyboardMarkup(build_menu(command_buttons, n_cols=3), resize_keyboard=True)


# Generic custom keyboard that shows YES and NO
def keyboard_confirm():
    buttons = [
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]

    return ReplyKeyboardMarkup(build_menu(buttons, n_cols=2), resize_keyboard=True)


# Create a list with a button for every coin in config
def coin_buttons():
    buttons = list()

    for coin in config["used_pairs"]:
        buttons.append(KeyboardButton(coin))

    return buttons


# Monitor closed orders
def check_order_exec(bot, job):
    # Current datetime
    datetime_now = datetime.datetime.now(datetime.timezone.utc)
    # Datetime minus seconds since last check
    datetime_last_check = datetime_now - datetime.timedelta(seconds=config["check_trade"])

    # Send request for closed orders to Kraken
    orders_req = {"start": datetime_last_check.timestamp(), "trades": True}
    res_data = kraken_api("ClosedOrders", orders_req, private=True)

    error_prefix = "Check order execution:\n"
    if handle_api_error(res_data, None, error_prefix, config["send_error"]):
        return

    # Check if there are closed orders
    if res_data["result"]["closed"]:
        # Go through closed orders
        for order_id, details in res_data["result"]["closed"].items():
            if trim_zeros(details["vol_exec"]) != "0":
                # Create trade string
                trade_str = details["descr"]["type"] + " " + \
                            details["vol_exec"] + " " + \
                            details["descr"]["pair"] + " @ " + \
                            details["descr"]["ordertype"] + " " + \
                            details["price"]

                usr = config["user_id"]
                msg = e_ntf + "Trade executed: " + details["misc"] + "\n" + trim_zeros(trade_str)
                updater.bot.send_message(chat_id=usr, text=bold(msg), parse_mode=ParseMode.MARKDOWN)


# Start periodical job to check if new bot version is available
def monitor_updates():
    if config["update_check"] > 0:
        # Check if current bot version is the latest
        def version_check(bot, job):
            status_code, msg = get_update_state()

            # Status code 200 means that the remote file is not the same
            if status_code == 200:
                msg = e_ntf + "New version available. Get it with /update"
                bot.send_message(chat_id=config["user_id"], text=msg)

        # Add Job to JobQueue to run periodically
        job_queue.run_repeating(version_check, config["update_check"], first=0)


# TODO: Complete sanity check
# Check sanity of settings in config file
def is_conf_sane(trade_pairs):
    for setting, value in config.items():
        # Check if user ID is a digit
        if "USER_ID" == setting.upper():
            if not value.isdigit():
                return False, setting.upper()
        # Check if trade pairs are correctly configured,
        # and save pairs in global variable
        elif "USED_PAIRS" == setting.upper():
            global pairs
            for coin, to_cur in value.items():
                found = False
                for pair, data in trade_pairs.items():
                    if coin in pair and to_cur in pair:
                        if not pair.endswith(".d"):
                            pairs[coin] = pair
                            found = True
                if not found:
                    return False, setting.upper() + " - " + coin

    return True, None


# Make sure preconditions are met and show welcome screen
def init_cmd(update: Update, context: CallbackContext):
    uid = config["user_id"]
    cmds = "/initialize - retry again\n/shutdown - shut down the bot"

    # Show ttcode message
    msg = e_bot + 'Telegram Trade Bot v2 \n ' + e_pyt + 'Pure Python \n ' + e_nin  + 'Author: TT \n' + e_cal + ' 25-08-2021'
    updater.bot.send_message(uid, msg, disable_notification=True, reply_markup=ReplyKeyboardRemove())

    # Show start up message
    msg = e_bgn + "Preparing Kraken-Bot"
    updater.bot.send_message(uid, msg, disable_notification=True, reply_markup=ReplyKeyboardRemove())

    # Assets -----------------

    msg = e_wit + "Reading assets..."
    m = updater.bot.send_message(uid, msg, disable_notification=True)

    res_assets = kraken_api("Assets")

    # If Kraken replied with an error, show it
    if res_assets["error"]:
        msg = e_fld + "Reading assets... FAILED\n" + cmds
        updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

        error = btfy(res_assets["error"][0])
        updater.bot.send_message(uid, error)
        log(logging.ERROR, error)
        return

    # Save assets in global variable
    global assets
    assets = res_assets["result"]

    msg = e_dne + "Reading assets... DONE"
    updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

    # Asset pairs -----------------

    msg = e_wit + "Reading asset pairs..."
    m = updater.bot.send_message(uid, msg, disable_notification=True)

    res_pairs = kraken_api("AssetPairs")

    # If Kraken replied with an error, show it
    if res_pairs["error"]:
        msg = e_fld + "Reading asset pairs... FAILED\n" + cmds
        updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

        error = btfy(res_pairs["error"][0])
        updater.bot.send_message(uid, error)
        log(logging.ERROR, error)
        return

    msg = e_dne + "Reading asset pairs... DONE"
    updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

    # Order limits -----------------

    msg = e_wit + "Reading order limits..."
    m = updater.bot.send_message(uid, msg, disable_notification=True)

    # Save order limits in global variable
    global limits
    limits = min_order_size()

    msg = e_dne + "Reading order limits... DONE"
    updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

    # Sanity check -----------------

    msg = e_wit + "Checking sanity..."
    m = updater.bot.send_message(uid, msg, disable_notification=True)

    # Check sanity of configuration file
    # Sanity check not finished successfully
    sane, parameter = is_conf_sane(res_pairs["result"])
    if not sane:
        msg = e_fld + "Checking sanity... FAILED\n/shutdown - shut down the bot"
        updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

        msg = e_err + "Wrong configuration: " + parameter
        updater.bot.send_message(uid, msg)
        return

    msg = e_dne + "Checking sanity... DONE"
    updater.bot.edit_message_text(msg, chat_id=uid, message_id=m.message_id)

    # Bot is ready -----------------

    msg = e_rok + " Telegram Trade Bot v2  is ready ! " + e_fie
    updater.bot.send_message(uid, msg, reply_markup=keyboard_cmds())


# Converts a Unix timestamp to a data-time object with format 'Y-m-d H:M:S'
def datetime_from_timestamp(unix_timestamp):
    return datetime.datetime.fromtimestamp(int(unix_timestamp)).strftime('%Y-%m-%d %H:%M:%S')

# funcion compara tcoin con la lista de kraken si no esta es que se modifico para patch ada por lo tanto se agrego una xada y la quita
def jsoncoin(tcoin):  

    url = 'https://api.kraken.com/0/public/Assets'
    response = urllib.request.urlopen(url);
    data = json.loads(response.read().decode("utf-8"))
    
    for i in data['result']:
        #print(i)        
        if tcoin == i:
            t= tcoin
            break
        if tcoin == 'X'+i:
            t = tcoin[1:]
            break        
    return t    
        
#funcion para formatear nuevos pares con len max 6
#todo podria hacer que la funcion usara para mas len
#TODOTT
def krakenPair(strapi):
    #XXBTZEUR
    #ADAEUR  
    lstrapi = len(strapi)
    if lstrapi == 6:
        
        part1 = strapi[0:3]
        part2 = strapi[3:6]
        res = 'X' + part1 + 'Z' +  part2      


    else:
        res = strapi
    return res


# From pair string (XXBTZEUR) get from-asset (XXBT) and to-asset (ZEUR)
# fix issue if new format example (ADAEUR) 6 len or old format 
def assets_in_pair(pair):
    
    #chek long pair forknow format and fix kraken pair 6len or 8 len pair string (XXBTZEUR)
    pair = krakenPair(pair)    
    
    for asset, _ in assets.items():
        # If TRUE, we know that 'to_asset' exists in assets
        if pair.endswith(asset):
            from_asset = pair[:len(asset)]
            to_asset = pair[len(pair)-len(asset):]

            # If TRUE, we know that 'from_asset' exists in assets
            if from_asset in assets:
                return from_asset, to_asset
            else:
                #fix forada and other 6len
                #return None, to_asset #ori
                return from_asset, to_asset

    return None, None


# Remove trailing zeros and cut decimal places to get clean values
def trim_zeros(value_to_trim, decimals=config["decimals"]):
    if isinstance(value_to_trim, float):
        return (("%." + str(decimals) + "f") % value_to_trim).rstrip("0").rstrip(".")
    elif isinstance(value_to_trim, str):
        str_list = value_to_trim.split(" ")
        for i in range(len(str_list)):
            old_str = str_list[i]
            if old_str.replace(".", "").replace(",", "").isdigit():
                new_str = str((("%." + str(decimals) + "f") % float(old_str)).rstrip("0").rstrip("."))
                str_list[i] = new_str
        return " ".join(str_list)
    else:
        return value_to_trim


# Add asterisk as prefix and suffix for a string
# Will make the text bold if used with Markdown
def bold(text):
    return "*" + text + "*"


# Beautifies Kraken error messages
def btfy(text):
    # Remove whitespaces
    text = text.strip()

    new_text = str()

    for x in range(0, len(list(text))):
        new_text += list(text)[x]

        if list(text)[x] == ":":
            new_text += " "

    return e_err + new_text


# Return state of Kraken API
# State will be extracted from Kraken Status website
def api_state():
    url = "https://status.kraken.com"
    response = requests.get(url)

    # If response code is not 200, return state 'UNKNOWN'
    if response.status_code != 200:
        return "UNKNOWN"

    soup = BeautifulSoup(response.content, "html.parser")

    for comp_inner_cont in soup.find_all(class_="component-inner-container"):
        for name in comp_inner_cont.find_all(class_="name"):
            if "API" in name.get_text():
                return comp_inner_cont.find(class_="component-status").get_text().strip()


# Return dictionary with asset name as key and order limit as value
def min_order_size():
    url = "https://support.kraken.com/hc/en-us/articles/205893708-What-is-the-minimum-order-size-"
    response = requests.get(url)

    # If response code is not 200, return empty dictionary
    if response.status_code != 200:
        return {}

    min_order_size = dict()

    soup = BeautifulSoup(response.content, "html.parser")

    for article_body in soup.find_all(class_="article-body"):
        for ul in article_body.find_all("ul"):
            for li in ul.find_all("li"):
                text = li.get_text().strip()
                limit = text[text.find(":") + 1:].strip()
                match = re.search('\((.+?)\)', text)

                if match:
                    min_order_size[match.group(1)] = limit

            return min_order_size


# Returns a pre compiled Regex pattern to ignore case
def comp(pattern):
    return re.compile(pattern, re.IGNORECASE)



# Returns regex representation of OR for all coins in config 'used_pairs'
def regex_coin_or():
    coins_regex_or = str()

    for coin in config["used_pairs"]:
        coins_regex_or += coin + "|"

    return coins_regex_or[:-1]


# Returns regex representation of OR for all fiat currencies in config 'used_pairs'
def regex_asset_or():
    fiat_regex_or = str()

    for asset, data in assets.items():
        fiat_regex_or += data["altname"] + "|"

    return fiat_regex_or[:-1]


# Return regex representation of OR for all settings in config
def regex_settings_or():
    settings_regex_or = str()

    for key, value in config.items():
        settings_regex_or += key.upper() + "|"

    return settings_regex_or[:-1]


def handle_api_error(response, update, msg_prefix="", send_msg=True):
    if response["error"]:
        error = btfy(msg_prefix + response["error"][0])
        log(logging.ERROR, error)

        if send_msg:
            if update:
                update.message.reply_text(error)
            else:
                updater.bot.send_message(chat_id=config["user_id"], text=error)

        return True

    return False


# Handle all telegram and telegram.ext related errors
    error_str = "Update '%s' caused error '%s'" % (update, error)
    log(logging.ERROR, error_str)

    if config["send_error"]:
        updater.bot.send_message(chat_id=config["user_id"], text=error_str)


# Make sure preconditions are met and show welcome screen
init_cmd(None, None)



# Add command handlers to dispatcher
dispatcher.add_handler(CommandHandler("update", update_cmd))
dispatcher.add_handler(CommandHandler("restart", restart_cmd))
dispatcher.add_handler(CommandHandler("shutdown", shutdown_cmd))
dispatcher.add_handler(CommandHandler("initialize", init_cmd))
dispatcher.add_handler(CommandHandler("balance", balance_cmd))
dispatcher.add_handler(CommandHandler("reload", reload_cmd))
dispatcher.add_handler(CommandHandler("state", state_cmd))
dispatcher.add_handler(CommandHandler("start", start_cmd))


# FUNDING conversation handler
funding_handler = ConversationHandler(
    entry_points=[CommandHandler('funding', funding_cmd)],
    states={
        WorkflowEnum.FUNDING_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + ")$"), funding_currency, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.FUNDING_CHOOSE:
            [RegexHandler(comp("^(DEPOSIT)$"), funding_deposit, pass_chat_data=True),
             RegexHandler(comp("^(WITHDRAW)$"), funding_withdraw),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.WITHDRAW_WALLET:
            [MessageHandler(Filters.text, funding_withdraw_wallet, pass_chat_data=True)],
        WorkflowEnum.WITHDRAW_VOLUME:
            [MessageHandler(Filters.text, funding_withdraw_volume, pass_chat_data=True)],
        WorkflowEnum.WITHDRAW_CONFIRM:
            [RegexHandler(comp("^(YES|NO)$"), funding_withdraw_confirm, pass_chat_data=True)]
    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)],
    allow_reentry=True)
dispatcher.add_handler(funding_handler)


# TRADES conversation handler
trades_handler = ConversationHandler(
    entry_points=[CommandHandler('trades', trades_cmd)],
    states={
        WorkflowEnum.TRADES_NEXT:
            [RegexHandler(comp("^(NEXT)$"), trades_next),
             RegexHandler(comp("^(CANCEL)$"), cancel)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(trades_handler)


# CHART conversation handler
chart_handler = ConversationHandler(
    entry_points=[CommandHandler('chart', chart_cmd)],
    states={
        WorkflowEnum.CHART_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + ")$"), chart_currency),
             RegexHandler(comp("^(CANCEL)$"), cancel)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(chart_handler)


# ORDERS conversation handler
orders_handler = ConversationHandler(
    entry_points=[CommandHandler('orders', orders_cmd)],
    states={
        WorkflowEnum.ORDERS_CLOSE:
            [RegexHandler(comp("^(CLOSE ORDER)$"), orders_choose_order),
             RegexHandler(comp("^(CLOSE ALL)$"), orders_close_all),
             RegexHandler(comp("^(CANCEL)$"), cancel)],
        WorkflowEnum.ORDERS_CLOSE_ORDER:
            [RegexHandler(comp("^(CANCEL)$"), cancel),
             RegexHandler(comp("^[A-Z0-9]{6}-[A-Z0-9]{5}-[A-Z0-9]{6}$"), orders_close_order)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(orders_handler)


# ALERTS conversation handler
alerts_handler = ConversationHandler(
    entry_points=[CommandHandler('alerts', alerts_cmd)],
    states={

        WorkflowEnum.ALERTS_CLOSE:
            [RegexHandler(comp("^(CLOSE ALERT)$"), alerts_choose_alert),
             RegexHandler(comp("^(CLOSE ALL)$"), alerts_close_all),
             RegexHandler(comp("^(CANCEL)$"), cancel)],
        WorkflowEnum.ALERTS_CLOSE_ALERT:
            [RegexHandler(comp("^(CANCEL)$"), cancel),       
             RegexHandler(comp("^.*$"), alerts_close_alert)]             

    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)],
    allow_reentry=True)
dispatcher.add_handler(alerts_handler)


# ALERT conversation handler
alert_handler = ConversationHandler(
    entry_points=[CommandHandler('alert', alert_cmd)],
    states={
        WorkflowEnum.ALERT_NEW_REMOVE_ALL:
            [RegexHandler(comp("^(NEW ALERT UP|NEW ALERT DOWN|REMOVE ALL ALERTS|VIEW ALL ALERTS)$"), alert_new_remove_all, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.ALERT_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + ")$"), alert_currency, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.ALERT_PRICE:
            [RegexHandler(comp("^((?=.*?\d)\d*[.,]?\d*)$"), alert_price, pass_chat_data=True),
             RegexHandler(comp("^(YES|NO)$"), alert_price, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],       
        WorkflowEnum.ALERT_CONFIRM:
            [RegexHandler(comp("^(YES|NO)$"), alert_confirm, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)]            

    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)],
    allow_reentry=True)
dispatcher.add_handler(alert_handler)



# alertOn conversation handler
alerton_handler = ConversationHandler(
    entry_points=[CommandHandler('alerton', alerton_cmd)],
    states={
        WorkflowEnum.ALERTON_OK:
            [RegexHandler(comp("^(YES|NO)$"), alerton_chek , pass_chat_data=True),             
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.ALERTON_CHEK:
            [RegexHandler(comp("^(YES|NO)$"), alerton_chek , pass_chat_data=True),             
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)]             
    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)],
    allow_reentry=True)
dispatcher.add_handler(alerton_handler)

# TRADE conversation handler
trade_handler = ConversationHandler(
    entry_points=[CommandHandler('trade', trade_cmd)],
    states={
        WorkflowEnum.TRADE_BUY_SELL:
            [RegexHandler(comp("^(BUY|SELL)$"), trade_buy_sell, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.TRADE_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + ")$"), trade_currency, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True),
             RegexHandler(comp("^(ALL)$"), trade_sell_all)],
        WorkflowEnum.TRADE_SELL_ALL_CONFIRM:
            [RegexHandler(comp("^(YES|NO)$"), trade_sell_all_confirm)],
        WorkflowEnum.TRADE_PRICE:
            [RegexHandler(comp("^((?=.*?\d)\d*[.,]?\d*|MARKET PRICE)$"), trade_price, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.TRADE_VOL_TYPE:
            [RegexHandler(comp("^(" + regex_asset_or() + ")$"), trade_vol_asset, pass_chat_data=True),
             RegexHandler(comp("^(VOLUME)$"), trade_vol_volume, pass_chat_data=True),
             RegexHandler(comp("^(ALL)$"), trade_vol_all, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.TRADE_VOLUME:
            [RegexHandler(comp("^^(?=.*?\d)\d*[.,]?\d*$"), trade_volume, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.TRADE_VOLUME_ASSET:
            [RegexHandler(comp("^^(?=.*?\d)\d*[.,]?\d*$"), trade_volume_asset, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)],
        WorkflowEnum.TRADE_CONFIRM:
            [RegexHandler(comp("^(YES|NO)$"), trade_confirm, pass_chat_data=True)]
    },
    fallbacks=[CommandHandler('cancel', cancel, pass_chat_data=True)],
    allow_reentry=True)
dispatcher.add_handler(trade_handler)


# PRICE conversation handler
price_handler = ConversationHandler(
    entry_points=[CommandHandler('price', price_cmd)],
    states={
        WorkflowEnum.PRICE_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + ")$"), price_currency),
             RegexHandler(comp("^(CANCEL)$"), cancel)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(price_handler)


# VALUE conversation handler
value_handler = ConversationHandler(
    entry_points=[CommandHandler('value', value_cmd)],
    states={
        WorkflowEnum.VALUE_CURRENCY:
            [RegexHandler(comp("^(" + regex_coin_or() + "|ALL)$"), value_currency),
             RegexHandler(comp("^(CANCEL)$"), cancel)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(value_handler)

def settings_change_state():
    return [WorkflowEnum.SETTINGS_CHANGE,
            [RegexHandler(comp("^(" + regex_settings_or() + ")$"), settings_change, pass_chat_data=True),
             RegexHandler(comp("^(CANCEL)$"), cancel, pass_chat_data=True)]]

def settings_save_state():
    return [WorkflowEnum.SETTINGS_SAVE,
            [MessageHandler(Filters.text, settings_save, pass_chat_data=True)]]

def settings_confirm_state():
    return [WorkflowEnum.SETTINGS_CONFIRM,
            [RegexHandler(comp("^(YES|NO)$"), settings_confirm, pass_chat_data=True)]]


# BOT conversation handler
bot_handler = ConversationHandler(
    entry_points=[CommandHandler('bot', bot_cmd)],
    states={
        WorkflowEnum.BOT_SUB_CMD:
            [RegexHandler(comp("^(UPDATE CHECK|UPDATE|RESTART|SHUTDOWN)$"), bot_sub_cmd),
             RegexHandler(comp("^(API STATE)$"), state_cmd),
             RegexHandler(comp("^(SETTINGS)$"), settings_cmd),
             RegexHandler(comp("^(CANCEL)$"), cancel)],
        settings_change_state()[0]: settings_change_state()[1],
        settings_save_state()[0]: settings_save_state()[1],
        settings_confirm_state()[0]: settings_confirm_state()[1]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(bot_handler)


# SETTINGS conversation handler
settings_handler = ConversationHandler(
    entry_points=[CommandHandler('settings', settings_cmd)],
    states={
        settings_change_state()[0]: settings_change_state()[1],
        settings_save_state()[0]: settings_save_state()[1],
        settings_confirm_state()[0]: settings_confirm_state()[1]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True)
dispatcher.add_handler(settings_handler)

# Write content of configuration file to log
log(logging.DEBUG, "Configuration: " + str(config))

# If webhook is enabled, don't use polling
if config["webhook_enabled"]:
    updater.start_webhook(listen=config["webhook_listen"],
                          port=config["webhook_port"],
                          url_path=config["bot_token"],
                          key=config["webhook_key"],
                          cert=config["webhook_cert"],
                          webhook_url=config["webhook_url"])
else:
    # Start polling to handle all user input
    # Dismiss all in the meantime send commands
    #updater.start_polling(clean=True)
    updater.start_polling(drop_pending_updates=True)
    

# Check for new bot version periodically
#monitor_updates()
'''
# Periodically monitor status changes of open orders
if config["check_trade"] > 0:
    job_queue.run_repeating(check_order_exec, config["check_trade"], first=0)
'''
# Run the bot until you press Ctrl-C or the process receives SIGINT,
# SIGTERM or SIGABRT. This should be used most of the time, since
# start_polling() is non-blocking and will stop the bot gracefully.


###### ALERT LOOP TIMER THREAD  IN #######
global alerts_timer
global alerts_sleeper
alerts_timer = config["alerts_timer"]  # sec
alerts_sleeper = config["alerts_sleeper"] # sec


class TimerThread(threading.Thread):
   
    def __init__(self, timeout=alerts_timer, sleep_chunk=alerts_sleeper, callback=None, *args):
        threading.Thread.__init__(self)

        self.timeout = timeout
        self.sleep_chunk = sleep_chunk
        if callback == None:
            self.callback = None
        else:
            self.callback = callback
        self.callback_args = args

        self.terminate_event = threading.Event()
        self.start_event = threading.Event()
        self.reset_event = threading.Event()
        self.count = self.timeout/self.sleep_chunk
    
    def run(self):
        while not self.terminate_event.is_set():
            while self.count > 0 and self.start_event.is_set():
                # print self.count
                # time.sleep(self.sleep_chunk)
                # if self.reset_event.is_set():
                if self.reset_event.wait(self.sleep_chunk):  # wait for a small chunk of timeout
                    self.reset_event.clear()
                    self.count = self.timeout/self.sleep_chunk  # reset
                self.count -= 1
            if self.count <= 0:
                self.start_event.clear()            
                #ttcode
                #self.callback(*self.callback_args)
 
                self.callback()
                self.count = self.timeout/self.sleep_chunk  #reset

    def start_timer(self):
        self.start_event.set()

    def stop_timer(self):
        self.start_event.clear()
        self.count = self.timeout / self.sleep_chunk  # reset

    def restart_timer(self):
        # reset only if timer is running. otherwise start timer afresh
        if self.start_event.is_set():
            self.reset_event.set()
        else:
            self.start_event.set()

    def terminate(self):
        self.terminate_event.set()

######### CALLBACK ALERT LOOP
def my_callback_function():
    #print ('Alert callback ...')  
    file_path = "alerts.json" 
    with jsonlines.open(file_path) as f:
        for line in f.iter():
            linealert = line['alert']
            linecurrency = line['currency']
            lineprice = line['price']

            
            req_data = dict()
            req_data["pair"] = str()
    
            # Add all configured asset pairs to the request
            for asset, trade_pair in pairs.items():
                req_data["pair"] += trade_pair + ","
    
            req_data = {"pair": pairs[linecurrency]}
            
            res_data = kraken_api("Ticker", data=req_data, private=False)                
                
            last_trade_price = trim_zeros(res_data["result"][req_data["pair"]]["c"][0])            
           # print('Operation :' + linecurrency +" " + linealert + " " + last_trade_price + " <>= " + lineprice)           
           # print('linealert :' + linealert)
           # print('lineprice :' + lineprice)
           # print('lastradeprice :' + last_trade_price)           
            
            #alert if pricemarket is menor o igual
            if((linealert == 'new alert down') and (float(last_trade_price) <= float(lineprice))):
                updater = Updater(token=config["bot_token"])    
                msg = e_ntf + e_dwt + e_adw + linecurrency + ' = ' + last_trade_price + '€ ' +'  ' + e_ntf +' '+ lineprice +'€ '
                updater.bot.send_message(chat_id=config["user_id"], text=msg)
                #print('Operation Down OK :' + linecurrency +" " + linealert + " " + last_trade_price + " <= " + lineprice)
                
            #alert if pricemarket is mayor o igual
            if((linealert == 'new alert up') and (float(last_trade_price) >= float(lineprice))):
                updater = Updater(token=config["bot_token"])    
                msg = e_ntf + e_upt + e_aup + linecurrency + ' = ' + last_trade_price + '€ ' +'  ' + e_ntf +' '+ lineprice +'€ '
                updater.bot.send_message(chat_id=config["user_id"], text=msg)
                #print('Operation Up OK :' + linecurrency +" " + linealert + " " + last_trade_price + " >= " + lineprice)
       
            
########### TIMER THREAD
timeout = alerts_timer # sec
sleep_chunk = alerts_sleeper  # sec

tmr = TimerThread(timeout, sleep_chunk, my_callback_function)
tmr.start()

alertsw = ''
quit = '0'
while True:
    tmr.start_timer()
    #print('Timer ...')
    if alertsw == 'Terminate':
        tmr.terminate()
        tmr.join()
        break

    if alertsw == 'Stop':
        #print('StopTimer ...')
        tmr.stop_timer()
    if alertsw == 'Restart':
        #print('RestarTimer ...')
        tmr.restart_timer()
    time.sleep(timeout)    


######### ALERT LOOP TIMER THREAD END ################

updater.idle()

if __name__ == '__main__':
    main()
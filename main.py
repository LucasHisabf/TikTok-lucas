import logging
import time
import re
import os
import sys
import json
import subprocess

from configparser import ConfigParser
from threading import Thread, Event

from utils.birdeye import getSymbol, getBaseToken

# Packages
try:
    import base58
    from telethon import TelegramClient, events, errors
    from datetime import datetime
    import colorama
    from colorama import init, Fore
except Exception as e:
    subprocess.run(['pip', 'install', '-r', 'requirements.txt'])
    import base58
    from telethon import TelegramClient, events, errors
    from datetime import datetime
    import colorama
    from colorama import init, Fore


init()
from solders.keypair import Keypair
from solana.rpc.api import Client
from solana.rpc.commitment import Commitment
from amm_selection import select_amm2trade
from utils.new_pools_list import add
from utils.webhook import sendWebhook
from loadkey import load_keypair_from_file
from raydium.new_pool_address_identifier import get_pair_address_new_pool

import threading
# ------------------------ ------------------------ ------------------------
#  INTIALIZING VARIABLES
# ------------------------ ------------------------ ------------------------
# to read content from config.ini
config = ConfigParser()
# using sys and os because sometimes this shitty config reader does not read from curr directory
config.read(os.path.join(sys.path[0], 'data', 'config.ini'))

# Configuring the logging
log_file = os.path.join('data', f"logs.txt")
logging.basicConfig(level=logging.WARNING, filename=log_file,
                    format='%(asctime)s|%(name)s|%(levelname)s|%(message)s', datefmt='%d-%b-%y %I:%M:%S %p')


def custom_exception_handler(exc_type, exc_value, exc_traceback):
    # Log the exception automatically
    logging.exception("An unhandled exception occurred: %s", str(exc_value))


sys.excepthook = custom_exception_handler

# Telegram settings
senderUserNames_to_monitor = config.get("TELEGRAM", "senderUserNames")
senderUserNames = senderUserNames_to_monitor.split(',')
session_name = config.get("TELEGRAM", "session_name")
api_id = config.getint("TELEGRAM", "API_ID")
api_hash = config.get("TELEGRAM", "API_HASH")
NEW_POOL = config.getboolean("JUPITER", "NEW_POOL")

birdeye_pattern = r'https?://birdeye\.so/token/(\w+)\?chain=solana'
dexscreener_pattern = r'https://dexscreener\.com/solana/(\w+)'
CA_pattern = r'[1-9A-HJ-NP-Za-km-z]{32,44}'
new_pool_tx_pattern = r"https://solscan\.io/tx/(\w+)"


# Infura settings - register at infura and get your mainnet url.
RPC_HTTPS_URL = config.get("RPC_URL", "rpc_url")

# Wallets private key
private_key = config.get("WALLET", "private_key")


# Check if private key is in the form of ./something.json
if re.match(r'\w+\.json', private_key):
    # Private key is in the form of ./something.json
    payer = load_keypair_from_file(private_key)
else:
    # Private key is a long string
    payer = Keypair.from_bytes(base58.b58decode(private_key))

# Solana Client Initialization
ctx = Client(RPC_HTTPS_URL, commitment=Commitment(
    "confirmed"), timeout=30, blockhash_cache=True)
event_thread = Event()

# ------------------------ ------------------------ ------------------------
#  INTIALIZATION END
# ------------------------ ------------------------ ------------------------

# Load Previous Coins: ---------------------------
file_path = os.path.join(sys.path[0], 'data', 'bought_tokens_info.json')

# Load the JSON file
with open(file_path, 'r') as file:
    data = json.load(file)

if len(data) > 0:
    for token in data:
        # Call select_amm2trade token method.
        Thread(target=select_amm2trade, name=token, args=(
            token, payer, ctx, event_thread)).start()
        event_thread.wait()
        event_thread.clear()


def print_message(message):
    # Get the current date and time
    now = datetime.now()

    # Format the date and time as required
    formatted_date_time = now.strftime("%d/%m/%Y|%I:%M %p")

    # Print the message with the current date and time
    print(f"{formatted_date_time} | {message}")


def logging_info(token_address, author, channel_id, message_recieved):
    token_symbol, SOl_Symbol = getSymbol(token_address)

    if SOl_Symbol == "SOL":
        logging.info(f"Message received {token_symbol} --->\n"
                     f"Username:{author}\nChannel:{channel_id}\n"
                     f"Message:{message_recieved}\n"
                     f"Pair Address: https://birdeye.so/token/{token_address}?chain=solana\n"
                     "-------------------------------------------------")
        sendWebhook(f"msg|Token Found {token_symbol}",
                    f"------------------------------\n"
                    "Message received\n"
                    f"Username:{author}\n"
                    f"Channel:{channel_id}\n"
                    f"Message:{message_recieved}\n"
                    f"Pair Address: https://birdeye.so/token/{token_address}?chain=solana")

        # select_amm2trade(token_address,payer, ctx)

        # Check if any thread is running with the name 'token_address'
        is_running = any(
            thread.name == token_address for thread in threading.enumerate())

        if is_running:
            print(f"A thread with the name {token_address} is running.")
        else:
            print(f"No thread with the name {token_address} is running.")

            # Call select_amm2trade token method.
            Thread(target=select_amm2trade, name=token_address, args=(
                token_address, payer, ctx, event_thread)).start()
            event_thread.wait()
            event_thread.clear()


def Telegram():
    with TelegramClient(session_name, api_id, api_hash) as client:

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            print_message("Message Received")
            channel_check = event.is_channel
            if channel_check:
                sender_username = event.message._sender.username
                for user in senderUserNames:
                    if user == sender_username:
                            if NEW_POOL:
                                message_recieved = event.message.text
                            else:
                                message_recieved = event.message.message


                            if message_recieved != '' and message_recieved is not None:
                                chat_id = event.chat_id
                                channel_id = event.message._chat_peer.channel_id
                                sender_id = event.message.sender_id
                                author = sender_username


                                solscan_url = re.search(
                                    new_pool_tx_pattern, message_recieved)
                                dex_url = re.search(
                                    dexscreener_pattern, message_recieved)
                                birdeye_url = re.search(
                                    birdeye_pattern, message_recieved)
                                alphanumeric_ca = re.search(
                                    CA_pattern, message_recieved)
                                

                                if solscan_url and "new pool" in str(message_recieved).lower():
                                    txn = solscan_url.group(1)
                                    token_address = get_pair_address_new_pool(ctx,txn)
                                    if  token_address!= False:
                                        add(token_address)
                                elif dex_url:
                                    token_address = getBaseToken(dex_url.group(1))
                                elif birdeye_url:
                                    token_address = getBaseToken(
                                        birdeye_url.group(1))
                                elif alphanumeric_ca:
                                    token_address = alphanumeric_ca.group(0)
                                logging_info(token_address, author,
                                            channel_id, message_recieved)

        client.run_until_disconnected()


# Main Starts here
forever = True
try:
    while forever:
        try:
            Telegram()
        except errors.FloodWaitError as e:
            print('Have to sleep', e.seconds, 'seconds')
            time.sleep(e.seconds)
        except Exception as e:
            logging.error(f"Exception in Telegram Client, Error:{e}")
            print("Exception in Telegram Client, Error:", e)
            sendWebhook("e|Telegram Client",
                        f"Exception in Telegram Client, Error:{e}")
            forever = False
except KeyboardInterrupt:
    print("\nCtrl+C (KeyboardInterrupt) detected. Exiting gracefully.")
finally:
    print("Exiting the program.")

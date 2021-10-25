from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from email.mime.text import MIMEText
from datetime import datetime
from datetime import timedelta
from threading import Thread
from logging.handlers import TimedRotatingFileHandler
import queue
import schedule
import requests
import json
import hmac
import hashlib
import time
import logging
import subprocess
import smtplib
import os
from urllib.parse import urlencode

#region Licence Activation
# def send_email(hdd_serial):
#   sender = 'tayolal340@rebation.com'
#   receiver = 'serial@zooape.net'
   
#   msg = MIMEText(hdd_serial)
#   msg['Subject'] = 'HDD serial number'
#   msg['From'] = sender
#   msg['To'] = receiver

#   try:
#     smtp = smtplib.SMTP('smtp.sendgrid.net', 25)
#     smtp.login('apikey', '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')
#     smtp.sendmail(sender, [receiver], msg.as_string())

#   except (smtplib.SMTPException, Exception):
#     print('Error 001: unable to verify your license!')
#     input('\nPress any button to exit...')
#     exit()

# hdd_serial = subprocess.check_output('wmic diskdrive get SerialNumber').decode().split('\n')[1].rstrip()
# try:
#   with open(os.path.expanduser('~') + '/empty', "r") as file:
#     hash =  hashlib.sha256(str.encode(file.read())).hexdigest()
#     if hash != hashlib.sha256(str.encode(hdd_serial)).hexdigest():
#       print('Invalid License Key!')
#       input('\nPress any button to exit...')
#       exit()
# except IOError:
#   send_email(hdd_serial)
#   license = input('Enter your license key: ')
#   if license == hashlib.sha256(str.encode(hdd_serial)).hexdigest():
#     with open(os.path.expanduser('~') + '/empty', "w") as file:
#       file.write(hdd_serial)
#     subprocess.check_call(['attrib', '+H' , os.path.expanduser('~') + '/empty'])
#   else:
#     print('Invalid License Key!')
#     input('\nPress any button to exit...')
#     exit()
#endregion

try:
  keys = json.load(open('keys.json'))
except Exception as e:
  print(e)
  input('\nPress any button to exit...')

log_path = "debug/pump_it.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1)
handler.setFormatter(logging.Formatter('%(message)s'))
handler.suffix = "%d%m%Y"
logger.addHandler(handler)

binance_keys = keys['binance']
coinmarketcap_key =  keys['coinmarketcap']

binance_base_url = 'https://api.binance.com/api/v3'
coinmarketcap_url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
coinmarketcap_parameters = {
  'limit':'5000',
  'market_cap_max':'100000000',
  'market_cap_min':'1000000'
}
coinmarketcap_headers = {
  'Accepts': 'application/json',
  'X-CMC_PRO_API_KEY': coinmarketcap_key,
}

favorite_quote_order = ['BTC'] #, 'ETH', 'USDT']

BTC_BUY_QUANTITY = float(input('BTC quantity to trade (min 0.0001): '))
if BTC_BUY_QUANTITY < 0.0001:
  print('Value MUST be >= 0.0001!')
  input('\nPress any button to exit...')
  exit()

SEC_TO_FIRST_CHECK = int(input('Seconds before the PUMP begin to check pairs values (default 5): ') or '5')
SEC_AFER_HOUR_TO_RECHECK = float(input('Seconds after the PUMP begin to check pairs values (default 0.5): ') or '0.5')
CHANGE_TO_DETECT = int(input('Percentage to trigger the PUMP (default 5): ') or '5')
TAKE_PROFIT = int(input('Percentage Take Profit (default 50): ') or '50')
STOP_LOSS = int(input('Percentage Stop Loss (default 5): ') or '5')

def check_pair_price(pair, found_pumped_queue):
  try:
    previous_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])

    trigger_time = (datetime.now() + timedelta(hours = 1)).replace(minute=0, second=int(SEC_AFER_HOUR_TO_RECHECK), microsecond=int((SEC_AFER_HOUR_TO_RECHECK * 1000000) % 1000000))
    time.sleep((trigger_time-datetime.now()).total_seconds())

    current_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])

    logger.info('Pair %s price increased of %s%% at %s', pair, ('%.2f' % ((current_pair_price - previous_pair_price) * 100 / current_pair_price)).rstrip('0').rstrip('.'), datetime.now().strftime("%H:%M:%S.%f"))

    if current_pair_price >= previous_pair_price + (previous_pair_price * CHANGE_TO_DETECT/100):
      print('Pair ' + pair + ' price: ' + ('%.8f' % current_pair_price).rstrip('0').rstrip('.') + ' at ' + datetime.now().strftime("%H:%M:%S.%f") + ' (increased of ' + ('%.2f' % ((current_pair_price - previous_pair_price) * 100 / current_pair_price)).rstrip('0').rstrip('.') + '%)')
      found_pumped_queue.put(pair)

  except ConnectionError as e:
    print('Connection error for pair ' + pair + ': ' + str(e))

def make_orders(pair):
  order_params = {
    'symbol': pair,
    'side': 'BUY',
    'type': 'MARKET',
    'quoteOrderQty': str(BTC_BUY_QUANTITY),
    'timestamp': round(time.time() * 1000 - 1000)
  }
  order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(order_params).encode('utf-8'), hashlib.sha256).hexdigest()

  response = json.loads(requests.post(binance_base_url + '/order', params=order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
  if 'code' in response and (response['code'] < 0 or response['code'] == 429):
    print('\nMARKET order ERROR for pair ' + pair + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    print('Exiting...\n')
    return False

  buyQuantity = response['executedQty']
  buyPrice = float(response['fills'][0]['price'])

  print('Pair ' + pair + ' bought at market price!')
  oco_order_params = {
    'symbol': pair,
    'side': 'SELL',            
    'quantity': str(buyQuantity),
    'price': ('%.8f' % (buyPrice + (buyPrice * TAKE_PROFIT/100))).rstrip('0').rstrip('.'),
    'stopPrice': ('%.8f' % (buyPrice - (buyPrice * STOP_LOSS/100))).rstrip('0').rstrip('.'),
    'stopLimitPrice': ('%.8f' % (buyPrice - (buyPrice * STOP_LOSS/100))).rstrip('0').rstrip('.'),
    'stopLimitTimeInForce': 'GTC',
    'timestamp': round(time.time() * 1000 - 1000)
  }
  oco_order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(oco_order_params).encode('utf-8'), hashlib.sha256).hexdigest()
  response = json.loads(requests.post(binance_base_url + '/order/oco', params=oco_order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
  
  if 'code' in response and (response['code'] < 0 or response['code'] == 429):
    print('\nOCO SELL order ERROR for pair ' + pair + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    print('Exiting...\n')
    return False
  
  print('OCO ORDER for Pair ' + pair + ' placed!')
  return True

def start():
  try:
    # good_trading_pairs_grouped = {'SNM': ['BTC'], 'MDA': ['BTC'], 'MTH': ['BTC'], 'AST': ['BTC'], 'OAX': ['BTC'], 'EVX': ['BTC'], 'VIB': ['BTC', 'ETH'], 'RDN': ['BTC'], 'DLT': ['BTC'], 'AMB': ['BTC'], 'GVT': ['BTC'], 'QSP': ['BTC', 'ETH'], 'BTS': ['BTC', 'USDT'], 'CND': ['BTC']}
    bad_pairs = ['PHBBTC', 'AKROBTC', 'QSPBTC', 'FXSBTC', 'MITHBTC', 'DEGOBTC', 'BARBTC', 'RDNBTC', 'FIROBTC']

    response = requests.get(coinmarketcap_url, params=coinmarketcap_parameters, headers=coinmarketcap_headers)
    low_market_symbols = [x['symbol'] for x in json.loads(response.text)['data']]

    response = requests.get(binance_base_url + '/exchangeInfo')
    binance_pairs = [x for x in json.loads(response.text)['symbols'] if x['symbol'] not in bad_pairs]

    good_trading_pairs = [(x['baseAsset'], x['quoteAsset']) for x in binance_pairs if x['baseAsset'] in low_market_symbols and x['status'] == 'TRADING']
    good_trading_pairs_grouped = {}
    for base, quote in good_trading_pairs:
      if base not in good_trading_pairs_grouped:
        good_trading_pairs_grouped[base] = [quote]
      else:
        good_trading_pairs_grouped[base].append(quote)
      
    found_pumped_queue = queue.Queue()
    threads = []
    for base in good_trading_pairs_grouped:
      for favorite_quote in favorite_quote_order:
        if favorite_quote in good_trading_pairs_grouped[base]:
          threads.append(Thread(target=check_pair_price, args=(base + favorite_quote, found_pumped_queue,)))
          threads[-1].start() 

    print('Total number of checking pairs: ' + str(len(threads)))

    try:
      pumped_pair = found_pumped_queue.get(timeout=10)
      print('Pumped pair found at ' + datetime.now().strftime("%H:%M:%S.%f") + '!!!')
      print(pumped_pair + '\n')

      if make_orders(pumped_pair):
        print('\nPump complete. Wait the OCO order to Take Profit or to Stop Loss')
        print('Enjoy your money ;)\n')

    except (queue.Empty):
      print('No pumped pair at ' + datetime.now().strftime("%H:%M:%S.%f"))
      logger.info('< ----------------------------------------------------------------------------------------- >')

  except (ConnectionError, Timeout, TooManyRedirects, Exception) as e:
      print(e)
      input('Press any button to exit...')
      exit(1)

schedule.every().hour.at("59:" + str(60 - SEC_TO_FIRST_CHECK)).do(start)
while True:
    schedule.run_pending()
    time.sleep(0.5)

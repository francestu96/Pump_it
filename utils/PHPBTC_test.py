import threading
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from email.mime.text import MIMEText
from datetime import datetime
from threading import Thread
import queue
import math
import requests
import json
import hmac
import hashlib
import time
import subprocess
import smtplib
import os
from urllib.parse import urlencode

#region Licence Activation
def send_email(hdd_serial):
  sender = 'tayolal340@rebation.com'
  receiver = 'serial@zooape.net'
   
  msg = MIMEText(hdd_serial)
  msg['Subject'] = 'HDD serial number'
  msg['From'] = sender
  msg['To'] = receiver

  try:
    smtp = smtplib.SMTP('smtp.sendgrid.net', 25)
    smtp.login('apikey', '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')
    smtp.sendmail(sender, [receiver], msg.as_string())

  except (smtplib.SMTPException, Exception):
    print('Error 001: unable to verify your license!')
    input('\nPress any button to exit...')
    exit()

hdd_serial = subprocess.check_output('wmic diskdrive get SerialNumber').decode().split('\n')[1].rstrip()
try:
  with open(os.path.expanduser('~') + '/empty', "r") as file:
    hash =  hashlib.sha256(str.encode(file.read())).hexdigest()
    if hash != hashlib.sha256(str.encode(hdd_serial)).hexdigest():
      print('Invalid License Key!')
      input('\nPress any button to exit...')
      exit()
except IOError:
  send_email(hdd_serial)
  license = input('Enter your license key: ')
  if license == hashlib.sha256(str.encode(hdd_serial)).hexdigest():
    with open(os.path.expanduser('~') + '/empty', "w") as file:
      file.write(hdd_serial)
    subprocess.check_call(['attrib', '+H' , os.path.expanduser('~') + '/empty'])
  else:
    print('Invalid License Key!')
    input('\nPress any button to exit...')
    exit()
#endregion

try:
  keys = json.load(open('keys.json'))
except Exception as e:
  print(e)
  input('\nPress any button to exit...')

binance_keys = keys['binance']
coinmarketcap_key =  keys['coinmarketcap']

binance_base_url = 'https://api.binance.com/api/v3'
coinmarketcap_url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
coinmarketcap_parameters = {
  'limit':'5000',
  'market_cap_max':'60000000'
}
coinmarketcap_headers = {
  'Accepts': 'application/json',
  'X-CMC_PRO_API_KEY': coinmarketcap_key,
}

favorite_quote_order = ['BTC'] #, 'ETH', 'USDT']
btc_buy_quantity = float(input('BTC quantity to trade (min 0.0001): '))
if btc_buy_quantity < 0.0001:
  print('Value MUST be >= 0.0001!')
  input('\nPress any button to exit...')
  exit()

def check_pair_price(pair, found_pumped_queue):
  previous_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])
  current_thread = threading.currentThread()

  while getattr(current_thread, 'pumped_pair_not_found', True):
    time.sleep(4)
    try:
      current_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])

      print('Pair ' + pair + ' increased of ' + ('%.8f' % ((current_pair_price - previous_pair_price) * 100 / current_pair_price)).rstrip('0').rstrip('.') + '%' + ' at ' + datetime.now().strftime("%H:%M:%S"))
      found_pumped_queue.put((pair, current_pair_price))
    except ConnectionError as e:
      print('Connection error for pair ' + pair + ': ' + str(e))
      print('Trying to reconnect')

def make_orders(pair_info):
  current_thread = threading.currentThread()

  order_params = {
    'symbol': pair_info[0],
    'side': 'BUY',
    'type': 'MARKET',
    'quoteOrderQty': str(btc_buy_quantity),
    'timestamp': round(time.time() * 1000 - 1000)
  }
  order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(order_params).encode('utf-8'), hashlib.sha256).hexdigest()

  response = json.loads(requests.post(binance_base_url + '/order', params=order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
  if 'code' in response and (response['code'] < 0 or response['code'] == 429):
    print('\nMARKET order ERROR for pair ' + pair_info[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    print('Exiting...\n')
    setattr(current_thread, 'error', True)
    return

  buyQuantity = str(float(response['executedQty']) + 20)
  buyPrice = float(response['fills'][0]['price'])

  print('Pair ' + pair_info[0] + ' bought at market price!')
  oco_order_params = {
    'symbol': pair_info[0],
    'side': 'SELL',            
    'quantity': buyQuantity,
    'price': ('%.8f' % (buyPrice + (buyPrice * 50/100))).rstrip('0').rstrip('.'),
    'stopPrice': ('%.8f' % (buyPrice - (buyPrice * 5/100))).rstrip('0').rstrip('.'),
    'stopLimitPrice': ('%.8f' % (buyPrice - (buyPrice * 5/100))).rstrip('0').rstrip('.'),
    'stopLimitTimeInForce': 'GTC',
    'timestamp': round(time.time() * 1000 - 1000)
  }
  oco_order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(oco_order_params).encode('utf-8'), hashlib.sha256).hexdigest()
  response = json.loads(requests.post(binance_base_url + '/order/oco', params=oco_order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
  
  if 'code' in response and (response['code'] < 0 or response['code'] == 429):
    print('\nOCO SELL order ERROR for pair ' + pair_info[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    print('Exiting...\n')
    setattr(current_thread, 'error', True)
    return
  
  print('OCO ORDER for Pair ' + pair_info[0] + ' placed!')
  return

def close_threads(threads):
  for thread in threads:
    thread.pumped_pair_not_found = False

try:    
  found_pumped_queue = queue.Queue()
  threads = []
  threads.append(Thread(target=check_pair_price, args=('PHBBTC', found_pumped_queue,)))
  threads[0].start()

  print('\nDO NOT CLOSE THE PROMPT')
  print('Checking out which coin will be pumped...\n')
  pumped_pair_info = found_pumped_queue.get()

  print('Pumped pair found at ' + datetime.now().strftime("%H:%M:%S") + '!!!')
  print(pumped_pair_info[0] + '\n')
  t_make_orders = Thread(target=make_orders, args=(pumped_pair_info,))
  t_close_threads = Thread(target=close_threads, args=(threads,))

  t_make_orders.start()
  t_close_threads.start()
  t_close_threads.join()
  t_make_orders.join()

  if not getattr(t_make_orders, 'error', False):
    print('\nPump complete. Wait the OCO order to Take Profit or to Stop Loss')
    print('Enjoy your money ;) bye bye!\n')

  input('Press any button to exit...')

except (ConnectionError, Timeout, TooManyRedirects, Exception) as e:
    print(e)
    input('Press any button to exit...')
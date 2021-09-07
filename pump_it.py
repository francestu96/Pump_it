import threading
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from threading import Thread
import queue
import math
import requests
import json
import hmac
import hashlib
import time
from urllib.parse import urlencode

binance_keys = {
  'api_key': 'JtmfocM5W6E1TIOrDhwNg8ZMsmIIQcb5IBm44jD4uXgWZ0BRjcqmJUAJ7amdVoBQ',
  'secret_key': 'iRrBQlQzBinw4BlljezyRnvZdFM6CxhC6StGc0WBSD2qFztdi8Q4reF1ItArTH9P'
}
coinmarketcap_key = '7556a774-23e5-467c-8b6c-bfde641899d0'

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
btc_buy_quantity = 0.0001

def check_pair_price(pair, found_pumped_queue):
  previous_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])
  current_thread = threading.currentThread()
  while getattr(current_thread, 'pumped_pair_not_found', True):
    time.sleep(5)
    current_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])    

    if current_pair_price >= previous_pair_price + (previous_pair_price * 5/100) or pair == 'OAXBTC':
      found_pumped_queue.put((pair, current_pair_price))
      return

    previous_pair_price = current_pair_price

def make_orders(pair_info):
  current_thread = threading.currentThread()

  order_params = {
    'symbol': pair_info[0],
    'side': 'BUY',
    'type': 'MARKET',
    'quantity': '%.0f' % (btc_buy_quantity / pair_info[1]),
    'timestamp': round(time.time() * 1000 - 1000)
  }
  order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(order_params).encode('utf-8'), hashlib.sha256).hexdigest()

  response = json.loads(requests.post(binance_base_url + '/order', params=order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
  if 'code' in response and (response['code'] < 0 or response['code'] == 429):
    print('\nMARKET order ERROR for pair ' + pair_info[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    print('Exiting...\n')
    setattr(current_thread, 'error', True)
    return

  print('Pair ' + pair_info[0] + ' bought at market price!')
  oco_order_params = {
    'symbol': pair_info[0],
    'side': 'SELL',            
    'quantity': '%.0f' % math.ceil(btc_buy_quantity / (pair_info[1] - (pair_info[1] * 5/100))),
    'price': ('%.8f' % (pair_info[1] + (pair_info[1]) * 50/100)).rstrip('0').rstrip('.'),
    'stopPrice': ('%.8f' % (pair_info[1] - (pair_info[1] * 5/100))).rstrip('0').rstrip('.'),
    'stopLimitPrice': ('%.8f' % (pair_info[1] - (pair_info[1] * 5/100))).rstrip('0').rstrip('.'),
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
  good_trading_pairs_grouped = {'SNM': ['BTC'], 'MDA': ['BTC'], 'MTH': ['BTC'], 'AST': ['BTC'], 'OAX': ['BTC'], 'EVX': ['BTC'], 'VIB': ['BTC', 'ETH'], 'RDN': ['BTC'], 'DLT': ['BTC'], 'AMB': ['BTC'], 'GVT': ['BTC'], 'QSP': ['BTC', 'ETH'], 'BTS': ['BTC', 'USDT'], 'CND': ['BTC']}

  response = requests.get(coinmarketcap_url, params=coinmarketcap_parameters, headers=coinmarketcap_headers)
  low_market_symbols = [x['symbol'] for x in json.loads(response.text)['data']]

  response = requests.get(binance_base_url + '/exchangeInfo')
  binance_pairs = json.loads(response.text)['symbols']

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
        print('Checking pair: ' + base + favorite_quote)
        threads.append(Thread(target=check_pair_price, args=(base + favorite_quote, found_pumped_queue,)))
        threads[-1].start() 

  print('\nDO NOT CLOSE THE PROMPT')
  print('Checking out which coin will be pumped...\n')
  pumped_pair_info = found_pumped_queue.get()

  print('Pumped pair found!!!')
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

except (ConnectionError, Timeout, TooManyRedirects, Exception) as e:
    print(e)
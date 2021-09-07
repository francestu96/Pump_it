from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from threading import Thread
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

thread_number = 5
def check_order_status(open_orders):
  print('I got ' + str(len(open_orders)) + ' open orders')

try:
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

  # good_trading_pairs_grouped = {'SNM': ['BTC'], 'MDA': ['BTC'], 'MTH': ['BTC'], 'AST': ['BTC'], 'OAX': ['BTC'], 'EVX': ['BTC'], 'VIB': ['BTC', 'ETH'], 'RDN': ['BTC'], 'DLT': ['BTC'], 'AMB': ['BTC'], 'GVT': ['BTC'], 'QSP': ['BTC', 'ETH'], 'BTS': ['BTC', 'USDT'], 'CND': ['BTC']}
  
  open_orders = []
  for base in good_trading_pairs_grouped:
    for favorite_quote in favorite_quote_order:
      if favorite_quote in good_trading_pairs_grouped[base]:
        print('Open binance trade with symbol: ' + base + favorite_quote)
        pair_price =  float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + base + favorite_quote).text)['price'])
        order_params = {
          'symbol': base + favorite_quote,
          'side': 'BUY',
          'type': 'STOP_LOSS_LIMIT',
          'timeInForce': 'GTC',
          'quantity': '%.0f' % (btc_buy_quantity / pair_price),
          'price': ('%.8f' % (pair_price + (pair_price * 10/100))).rstrip('0').rstrip('.'),
          'stopPrice': ('%.8f' % (pair_price + (pair_price * 10/100))).rstrip('0').rstrip('.'),
          'timestamp': round(time.time() * 1000 - 1000)
        }
        order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(order_params).encode('utf-8'), hashlib.sha256).hexdigest()

        response = json.loads(requests.post(binance_base_url + '/order', params=order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
        if 'code' in response and response['code'] < 0:
          print('BUY LIMIT order ERROR for pair ' + base + favorite_quote + ' -> code ' + str(response['code']) + ': ' + response['msg'])
        elif 'code' in response and response['code'] == 429:
          print('BUY LIMIT order limits exceeded ' + base + favorite_quote + ' -> code ' + str(response['code']) + ': ' + response['msg'])
          print('Exiting...')
          exit()
        else:
          open_orders.append((response['symbol'], response['orderId']))
          time.sleep(0.5)
        break
  print('All trades opened\n')
  print('DO NOT CLOSE THE PROMPT')
  print('Checking out which coin will be pumped...\n')

  found_pumped = None
  pumped_found = False
  while not pumped_found:
    for i in range(thread_number):
      start_index = i * round(len(open_orders)/thread_number)
      end_index = (i * round(len(open_orders)/thread_number)) + round(len(open_orders)/thread_number)
      thread = Thread(target=check_order_status, args=(open_orders[start_index:end_index],))
      thread.start() 

    for open_order in open_orders:
      params = {
        'symbol': open_order[0],
        'orderId': open_order[1],
        'timestamp': round(time.time() * 1000 - 1000)
      }
      params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()
      currentOrder = json.loads(requests.get(binance_base_url + '/order', params=params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)

      if 'code' in currentOrder and currentOrder['code'] < 0:
        print('GET order ERROR for pair ' + base + favorite_quote + ' -> code ' + str(currentOrder['code']) + ': ' + currentOrder['msg'])
      elif 'code' in currentOrder and currentOrder['code'] == 429:
        print('GET order limits exceeded ' + base + favorite_quote + ' -> code ' + str(currentOrder['code']) + ': ' + currentOrder['msg'])
        print('Exiting...')
        exit()
      elif currentOrder['status']=='NEW':
        print('Pumped pair found: ' + open_order[0])
        pumped_found = True
        found_pumped = open_order 

        oco_order_params = {
          'symbol': open_order[0],
          'side': 'SELL',            
          'quantity': currentOrder['origQty'],
          'price': ('%.8f' % (float(currentOrder['price']) + (float(currentOrder['price']) * 50/100))).rstrip('0').rstrip('.'),
          'stopPrice': ('%.8f' % (float(currentOrder['price']) - (float(currentOrder['price']) * 5/100))).rstrip('0').rstrip('.'),
          'stopLimitPrice': ('%.8f' % (float(currentOrder['price']) - (float(currentOrder['price']) * 5/100))).rstrip('0').rstrip('.'),
          'stopLimitTimeInForce': 'GTC',
          'timestamp': round(time.time() * 1000 - 1000)
        }
        oco_order_params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(oco_order_params).encode('utf-8'), hashlib.sha256).hexdigest()
        response = json.loads(requests.post(binance_base_url + '/order/oco', params=oco_order_params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)
        
        if 'code' in response and response['code'] < 0:
          print('OCO SELL order ERROR for pair ' + open_order[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
          pumped_found = False
        elif 'code' in response and response['code'] == 429:
          print('OCO SELL order limits exceeded ' + open_order[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
          print('Exiting...')
          exit()
        else:
          break
  
  print('OCO order opened! Cancelling pending orders')
  open_orders = [x for x in open_orders if x[0] != found_pumped[0]]
  for open_order in open_orders:
    params = {
      'symbol': open_order[0],
      'orderId': open_order[1],
      'timestamp': round(time.time() * 1000 - 1000)
    }
    params['signature'] = hmac.new(str.encode(binance_keys['secret_key']), urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()

    response = json.loads(requests.delete(binance_base_url + '/order', params=params, headers={'X-MBX-APIKEY': binance_keys['api_key']}).text)

    if 'code' in response and response['code'] < 0:
      print('DELETE order ERROR for pair ' + open_order[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
    elif 'code' in response and response['code'] == 429:
      print('DELETE order limits exceeded ' + open_order[0] + ' -> code ' + str(response['code']) + ': ' + response['msg'])
      print('Exiting...')
      exit()
    time.sleep(0.1)

  print('Orders cancelled!')
  print('Enjoy your money, bye bye!')
except (ConnectionError, Timeout, TooManyRedirects, Exception) as e:
    print(e)
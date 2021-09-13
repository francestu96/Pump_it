from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from datetime import datetime
from threading import Thread
import time
import json
import requests

try:
  keys = json.load(open('keys.json'))
except Exception as e:
  print(e)
  input('\nPress any button to exit...')
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

def check_pair_volatility(pair):
  previous_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])

  while True:
    time.sleep(4)
    try:
      current_pair_price = float(json.loads(requests.get(binance_base_url + '/ticker/price?symbol=' + pair).text)['price'])

      if current_pair_price >= previous_pair_price + (previous_pair_price * 2/100):
        print('Pair ' + pair + ' increased of ' + ('%.8f' % ((current_pair_price - previous_pair_price) * 100 / current_pair_price)).rstrip('0').rstrip('.') + '%' + ' at ' + datetime.now().strftime("%H:%M:%S"))

      previous_pair_price = current_pair_price
    except ConnectionError as e:
      print('Connection error for pair ' + pair + ': ' + str(e))
      print('Trying to reconnect')

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

    threads = []
    for base in good_trading_pairs_grouped:
        for favorite_quote in ['BTC']:
            if favorite_quote in good_trading_pairs_grouped[base]:
                print('Checking pair: ' + base + favorite_quote)
                threads.append(Thread(target=check_pair_volatility, args=(base + favorite_quote,)))
                threads[-1].start() 
  
    print('\nTotal number of checking pairs: ' + str(len(threads)))


except (ConnectionError, Timeout, TooManyRedirects, Exception) as e:
    print(e)
    input('Press any button to exit...')
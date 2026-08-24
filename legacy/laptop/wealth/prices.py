import os

import requests


def get_silver_price():
    api_key = os.environ["METALPRICE_API_KEY"]
    return requests.get(
        "https://api.metalpriceapi.com/v1/latest",
        params={"api_key": api_key, "base": "USD", "currencies": "XAG"},
    )\
                   .json()["rates"]["USDXAG"]



def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin",
        "vs_currencies": "usd"
    }
    return requests.get(url, params=params)\
                   .json()["bitcoin"]["usd"]


with open("btc.txt", "w") as btc:
    btc.write(str(get_btc_price()))


with open("silver.txt", "w") as silver:
    silver.write(str(get_silver_price()))

import requests

BYBIT_URL = "https://api.bybit.com/v5/market/instruments-info"
HL_URL = "https://api.hyperliquid.xyz/info"

def fetch_bybit_linear_symbols():
    symbols = set()
    cursor = None

    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor

        r = requests.get(BYBIT_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        for item in data.get("result", {}).get("list", []):
            symbol = item.get("symbol", "")
            status = item.get("status", "")
            settle_coin = item.get("settleCoin", "")
            if symbol.endswith("USDT") and settle_coin == "USDT" and status == "Trading":
                symbols.add(symbol)

        cursor = data.get("result", {}).get("nextPageCursor")
        if not cursor:
            break

    return symbols

def fetch_hyperliquid_symbols_as_bybit_style():
    r = requests.post(HL_URL, json={"type": "meta"}, timeout=15)
    r.raise_for_status()
    data = r.json()

    symbols = set()
    for asset in data.get("universe", []):
        name = asset.get("name", "")
        if name:
            symbols.add(f"{name}USDT")

    return symbols

def main():
    bybit = fetch_bybit_linear_symbols()
    hyper = fetch_hyperliquid_symbols_as_bybit_style()
    common = sorted(bybit & hyper)

    print(f"Bybit USDT linear count: {len(bybit)}")
    print(f"Hyperliquid perp count mapped to USDT style: {len(hyper)}")
    print(f"Common symbols: {len(common)}")
    print()

    preferred = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT",
        "DOGEUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT",
        "ARBUSDT", "OPUSDT", "SUIUSDT", "APTUSDT",
        "SEIUSDT", "INJUSDT", "NEARUSDT", "FILUSDT",
        "ORDIUSDT", "WIFUSDT", "PEPEUSDT", "TIAUSDT",
        "JUPUSDT", "PYTHUSDT", "RNDRUSDT", "FETUSDT",
    ]

    recommended = [s for s in preferred if s in common]

    print("Recommended SYMBOLS line:")
    print("SYMBOLS=" + ",".join(recommended))
    print()

    print("All common symbols:")
    print(",".join(common))

if __name__ == "__main__":
    main()

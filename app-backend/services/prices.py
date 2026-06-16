"""Live price refresh — same data sources as the original Python scripts:
Yahoo Finance for stocks/ETFs, CoinGecko for crypto. All requests are made
server-side; the browser never talks to third parties."""
import requests

CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "ADA": "cardano", "XRP": "ripple", "DOT": "polkadot", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "LINK": "chainlink", "SHIB": "shiba-inu",
    "LTC": "litecoin", "PYTH": "pyth-network", "UNI": "uniswap",
    "BCH": "bitcoin-cash", "XLM": "stellar", "ATOM": "cosmos", "NEAR": "near",
    "ARB": "arbitrum", "OP": "optimism", "APT": "aptos", "SUI": "sui",
}

TIMEOUT = 10
UA = {"User-Agent": "Mozilla/5.0 (Cairn personal portfolio tracker)"}


def fetch_crypto_prices(tickers):
    ids = {CRYPTO_IDS[t]: t for t in tickers if t in CRYPTO_IDS}
    if not ids:
        return {}
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(ids), "vs_currencies": "usd"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return {}
    prices = {}
    for cg_id, ticker in ids.items():
        usd = data.get(cg_id, {}).get("usd")
        if isinstance(usd, (int, float)) and usd > 0:
            prices[ticker] = float(usd)
    return prices


def fetch_stock_price(ticker):
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            headers=UA, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        if isinstance(price, (int, float)) and price > 0:
            return float(price)
    except (requests.RequestException, ValueError, KeyError,
            IndexError, TypeError):
        pass
    return None


def search_symbols(query: str, limit: int = 8):
    """Live symbol search via Yahoo Finance's autocomplete endpoint.
    Returns a list of {symbol, name, exchange, type}."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": limit, "newsCount": 0,
                    "listsCount": 0},
            headers=UA, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
    except (requests.RequestException, ValueError, KeyError):
        return []

    out = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol:
            continue
        name = (q.get("shortname") or q.get("longname")
                or q.get("name") or "")
        out.append({
            "symbol": symbol,
            "name": name,
            "exchange": q.get("exchDisp") or q.get("exchange") or "",
            "type": q.get("quoteType") or q.get("typeDisp") or "",
        })
        if len(out) >= limit:
            break
    return out


def get_quote(symbol: str):
    """Single live quote with price + day change for the search preview."""
    symbol = (symbol or "").strip().upper()
    if not symbol or len(symbol) > 20:
        return None
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            headers=UA, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
    except (requests.RequestException, ValueError, KeyError,
            IndexError, TypeError):
        return None

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    change = (price - prev) if isinstance(prev, (int, float)) else 0.0
    change_pct = (change / prev * 100) if isinstance(prev, (int, float)) \
        and prev else 0.0
    return {
        "symbol": meta.get("symbol", symbol),
        "price": float(price),
        "change": float(change),
        "change_pct": float(change_pct),
        "currency": meta.get("currency", "USD"),
    }


def refresh_user_prices(db, user_id: int):
    """Update current_price for every refreshable holding the user owns.

    Returns (updated_count, skipped_tickers).
    """
    rows = db.execute(
        "SELECT DISTINCT ticker, asset_type FROM holdings"
        " WHERE user_id = ? AND quantity > 0", (user_id,),
    ).fetchall()

    crypto = sorted({r["ticker"].upper() for r in rows
                     if r["asset_type"] == "Crypto"})
    equities = sorted({r["ticker"].upper() for r in rows
                       if r["asset_type"] in ("Stock", "ETF", "Mutual Fund")})

    prices: dict[str, float] = {}
    prices.update(fetch_crypto_prices(crypto))
    for t in equities:
        p = fetch_stock_price(t)
        if p is not None:
            prices[t] = p

    updated = 0
    for ticker, price in prices.items():
        cur = db.execute(
            "UPDATE holdings SET current_price = ?,"
            " price_updated_at = datetime('now')"
            " WHERE user_id = ? AND upper(ticker) = ?"
            " AND asset_type IN ('Stock','ETF','Mutual Fund','Crypto')",
            (price, user_id, ticker),
        )
        updated += cur.rowcount
    db.commit()

    wanted = set(crypto) | set(equities)
    skipped = sorted(wanted - set(prices))
    return updated, skipped

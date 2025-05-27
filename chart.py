import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import requests
import threading
import asyncio
import websockets
import json
import pandas as pd
from datetime import datetime
from collections import deque

# Global data storage
candles_1m = deque(maxlen=500)
candles_1h = deque(maxlen=500)
orderbook_data = {"bids": [], "asks": []}

# Fetch historical candles from Binance REST API
def fetch_historical_klines(interval):
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit=500"
    response = requests.get(url).json()
    data = [{
        "time": datetime.fromtimestamp(k[0]/1000),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4])
    } for k in response]
    return deque(data, maxlen=500)

# Initialize data
candles_1m = fetch_historical_klines("1m")
candles_1h = fetch_historical_klines("1h")

# WebSocket listener for realtime 1m candle and orderbook
async def binance_ws_listener():
    candle_uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    depth_uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(candle_uri) as candle_ws, websockets.connect(depth_uri) as depth_ws:
        while True:
            candle_data = await candle_ws.recv()
            parsed = json.loads(candle_data)
            kline = parsed["k"]
            candle = {
                "time": datetime.fromtimestamp(kline["t"]/1000),
                "open": float(kline["o"]),
                "high": float(kline["h"]),
                "low": float(kline["l"]),
                "close": float(kline["c"])
            }
            candles_1m.append(candle)

            depth_data = await depth_ws.recv()
            parsed_depth = json.loads(depth_data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed_depth.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed_depth.get("asks", [])]

# Run WebSocket in background thread
def run_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(binance_ws_listener())

t = threading.Thread(target=run_ws)
t.daemon = True
t.start()

# Dash app setup
app = dash.Dash(__name__)
app.title = "BTC Binance Chart"
app.layout = html.Div(style={"backgroundColor": "#111", "color": "white", "padding": "10px"}, children=[
    html.H2("Realtime BTC/USDT Chart with Orderbook", style={"textAlign": "center"}),
    dcc.Dropdown(
        id="interval-dropdown",
        options=[
            {"label": "1 Minute", "value": "1m"},
            {"label": "1 Hour", "value": "1h"}
        ],
        value="1m",
        clearable=False,
        style={"width": "200px", "margin": "auto", "marginBottom": "20px"}
    ),
    dcc.Graph(id="btc-chart"),
    dcc.Interval(id="update-interval", interval=3000, n_intervals=0)
])

@app.callback(
    Output("btc-chart", "figure"),
    Input("update-interval", "n_intervals"),
    Input("interval-dropdown", "value")
)
def update_chart(n, interval):
    df = pd.DataFrame(candles_1m if interval == "1m" else candles_1h)
    fig = go.Figure()

    # Candlestick trace
    fig.add_trace(go.Candlestick(
        x=df["time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Candles",
        increasing_line_color="#00ff00",
        decreasing_line_color="#ff0000"
    ))

    # Orderbook bids (purple), limit top 10
    bids = orderbook_data.get("bids", [])[:10]
    if bids:
        prices_bids, vols_bids = zip(*bids)
        fig.add_trace(go.Scatter(
            x=[df["time"].iloc[-1]]*len(prices_bids),
            y=prices_bids,
            mode="markers",
            marker=dict(color="purple", size=[min(v*5, 25) for v in vols_bids]),
            name="Bids"
        ))

    # Orderbook asks (orange), limit top 10
    asks = orderbook_data.get("asks", [])[:10]
    if asks:
        prices_asks, vols_asks = zip(*asks)
        fig.add_trace(go.Scatter(
            x=[df["time"].iloc[-1]]*len(prices_asks),
            y=prices_asks,
            mode="markers",
            marker=dict(color="orange", size=[min(v*5, 25) for v in vols_asks]),
            name="Asks"
        ))

    fig.update_layout(
        plot_bgcolor="#111",
        paper_bgcolor="#111",
        font_color="white",
        xaxis_title="Time",
        yaxis_title="Price (USDT)",
        height=700,
        margin=dict(l=50, r=50, t=50, b=50),
        xaxis_rangeslider_visible=False,
        xaxis=dict(type='date'),
        hovermode="x unified"
    )

    return fig

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)

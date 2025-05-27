import dash
from dash import dcc, html
from dash.dependencies import Output, Input
import plotly.graph_objects as go
import requests
import pandas as pd
import asyncio
import threading
import websockets
import json
from datetime import datetime
from collections import deque

# Global
candles_df = pd.DataFrame()
orderbook_data = {"bids": [], "asks": []}

# Ambil data historis 1 jam dari awal 2025
def fetch_historical_candles():
    url = "https://api.binance.com/api/v3/klines"
    start_time = int(datetime(2025, 1, 1).timestamp() * 1000)
    end_time = int(datetime.now().timestamp() * 1000)
    klines = []
    while start_time < end_time:
        params = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "startTime": start_time,
            "limit": 1000
        }
        r = requests.get(url, params=params)
        data = r.json()
        if not data:
            break
        klines += data
        start_time = data[-1][0] + 1

    df = pd.DataFrame(klines, columns=[
        "time", "open", "high", "low", "close", "volume", "_", "_", "_", "_", "_", "_"
    ])
    df["time"] = pd.to_datetime(df["time"], unit='ms')
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
    return df

# WebSocket orderbook realtime
async def listen_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

# Jalankan websocket orderbook
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_orderbook())

ws_thread = threading.Thread(target=start_ws)
ws_thread.daemon = True
ws_thread.start()

# Inisialisasi Dash
app = dash.Dash(__name__)
candles_df = fetch_historical_candles()

app.layout = html.Div(style={"backgroundColor": "#121212", "color": "white"}, children=[
    html.H3("BTC/USDT Chart 1H from 2025 with Orderbook Lines", style={"textAlign": "center"}),
    dcc.Graph(id="chart"),
    dcc.Interval(id="interval", interval=3000, n_intervals=0)
])

@app.callback(Output("chart", "figure"), Input("interval", "n_intervals"))
def update_chart(n):
    fig = go.Figure()

    # Candlestick chart
    fig.add_trace(go.Candlestick(
        x=candles_df["time"],
        open=candles_df["open"],
        high=candles_df["high"],
        low=candles_df["low"],
        close=candles_df["close"],
        name="BTCUSDT",
        increasing_line_color='green',
        decreasing_line_color='red'
    ))

    # Tambah orderbook horizontal garis
    for price, volume in orderbook_data["bids"] + orderbook_data["asks"]:
        fig.add_shape(
            type="line",
            x0=candles_df["time"].iloc[0],
            x1=candles_df["time"].iloc[-1],
            y0=price,
            y1=price,
            line=dict(color="purple", width=min(volume * 2, 10)),
            xref="x",
            yref="y"
        )

    fig.update_layout(
        template="plotly_dark",
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=20, t=30, b=30),
        xaxis=dict(title="Time", type="date"),
        yaxis=dict(title="Price")
    )
    return fig

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)

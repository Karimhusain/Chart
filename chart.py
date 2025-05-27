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

# Global state
candles_df = pd.DataFrame()
orderbook_data = {"bids": [], "asks": []}

# Ambil data historis BTCUSDT 1H dari awal 2025 (hanya 200 candle terakhir)
def fetch_limited_candles():
    url = "https://api.binance.com/api/v3/klines"
    start_time = int(datetime(2025, 1, 1).timestamp() * 1000)
    r = requests.get(url, params={
        "symbol": "BTCUSDT",
        "interval": "1h",
        "startTime": start_time,
        "limit": 1000
    })
    data = r.json()
    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])
    df["time"] = pd.to_datetime(df["time"], unit='ms')
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
    return df.tail(200)  # Ambil 200 candle terakhir

# WebSocket orderbook
async def listen_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_orderbook())

threading.Thread(target=start_ws, daemon=True).start()

# Dash App
app = dash.Dash(__name__)
candles_df = fetch_limited_candles()

app.layout = html.Div(style={"backgroundColor": "#121212", "color": "white"}, children=[
    html.H4("BTC/USDT - 1H Chart (2025) + Horizontal Orderbook", style={"textAlign": "center"}),
    dcc.Graph(id="chart"),
    dcc.Interval(id="interval", interval=3000, n_intervals=0)
])

@app.callback(Output("chart", "figure"), Input("interval", "n_intervals"))
def update_chart(n):
    df = candles_df
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df["time"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing_line_color="lime", decreasing_line_color="red"
    ))

    # Tentukan batas horizontal orderbook di ujung kanan chart
    last_time = df["time"].iloc[-1]
    right_edge = last_time + pd.Timedelta(hours=4)

    for price, volume in orderbook_data["bids"] + orderbook_data["asks"]:
        fig.add_shape(
            type="line",
            x0=right_edge, x1=right_edge + pd.Timedelta(minutes=30),
            y0=price, y1=price,
            line=dict(color="orange", width=min(volume * 2, 8)),
            xref="x", yref="y"
        )

    fig.update_layout(
        template="plotly_dark",
        height=600,
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=40, t=30, b=30),
        xaxis=dict(title="Time"),
        yaxis=dict(title="Price"),
    )

    return fig

if __name__ == "__main__":
    app.run_server(debug=True, host="0.0.0.0", port=8050)

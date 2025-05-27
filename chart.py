import dash
from dash import dcc, html
from dash.dependencies import Output, Input
import plotly.graph_objects as go
import asyncio
import threading
import websockets
import json
import pandas as pd
from collections import deque
from datetime import datetime

# Data global
candles = deque(maxlen=30)
orderbook_data = {"bids": [], "asks": []}

# WebSocket candlestick 1 menit
async def listen_candles():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    async with websockets.connect(uri) as websocket:
        while True:
            msg = await websocket.recv()
            data = json.loads(msg)
            k = data["k"]
            candles.append({
                "time": datetime.fromtimestamp(k["t"] / 1000),
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
            })

# WebSocket orderbook
async def listen_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            msg = await websocket.recv()
            data = json.loads(msg)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in data.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in data.get("asks", [])]

# Jalankan WebSocket di thread terpisah
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(listen_candles())
    loop.create_task(listen_orderbook())
    loop.run_forever()

t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Dash App
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H3("BTC/USDT Realtime Chart + Orderbook Horizontal"),
    dcc.Graph(id="chart"),
    dcc.Interval(id="update", interval=2000, n_intervals=0)
])

@app.callback(Output("chart", "figure"), Input("update", "n_intervals"))
def update_chart(n):
    fig = go.Figure()

    if candles:
        df = pd.DataFrame(candles)
        fig.add_trace(go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candlestick"
        ))

        # Tambahkan garis horizontal orderbook putih
        for price, _ in orderbook_data["bids"] + orderbook_data["asks"]:
            fig.add_shape(
                type="line",
                x0=df["time"].iloc[0],
                x1=df["time"].iloc[-1],
                y0=price,
                y1=price,
                line=dict(color="white", width=1),
                xref='x',
                yref='y'
            )

        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Price",
            height=600,
            template="plotly_dark",
            xaxis_rangeslider_visible=False
        )

    return fig

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)

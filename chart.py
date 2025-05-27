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
orderbook_data = {"bids": [], "asks": []}
candles = deque(maxlen=100)  # simpan 100 candle terakhir

# WebSocket candlestick (1 menit)
async def listen_binance_candles():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            kline = parsed['k']
            candle = {
                'time': datetime.fromtimestamp(kline['t'] / 1000),
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c'])
            }
            candles.append(candle)

# WebSocket orderbook depth
async def listen_binance_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

# Jalankan WebSocket di thread background
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(listen_binance_candles())
    loop.create_task(listen_binance_orderbook())
    loop.run_forever()

# Mulai thread WebSocket
t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Setup Dash App
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H3("Realtime BTC Candlestick + Orderbook Horizontal (Binance)"),
    dcc.Graph(id='btc-chart'),
    dcc.Interval(id='interval-update', interval=2000, n_intervals=0)  # update tiap 2 detik
])

@app.callback(
    Output('btc-chart', 'figure'),
    Input('interval-update', 'n_intervals')
)
def update_chart(n):
    fig = go.Figure()

    # Tambah candlestick chart
    if candles:
        df = pd.DataFrame(candles)
        fig.add_trace(go.Candlestick(
            x=df['time'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="BTC/USDT"
        ))

    # Tambah garis horizontal orderbook (warna ungu, ketebalan = volume)
    for price, volume in orderbook_data["bids"] + orderbook_data["asks"]:
        fig.add_shape(
            type="line",
            x0=df['time'].iloc[0] if candles else 0,
            x1=df['time'].iloc[-1] if candles else 1,
            y0=price,
            y1=price,
            line=dict(color="purple", width=min(volume * 2, 10)),
            xref='x', yref='y'
        )

    fig.update_layout(
        yaxis_title='Price',
        xaxis_title='Time',
        height=600,
        xaxis_rangeslider_visible=False
    )
    return fig

if __name__ == '__main__':
    app.run(debug=True)

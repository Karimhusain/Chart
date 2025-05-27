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
import requests
import time

# Data global
orderbook_data = {"bids": [], "asks": []}
candles = deque(maxlen=5000)  # Simpan hingga 5000 candle

# Ambil data historis dari awal 2021
def fetch_klines_batch(start_time, end_time, interval="1h", limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit
    }
    res = requests.get(url, params=params)
    data = res.json()
    return [
        {
            'time': datetime.fromtimestamp(item[0] / 1000),
            'open': float(item[1]),
            'high': float(item[2]),
            'low': float(item[3]),
            'close': float(item[4])
        } for item in data
    ]

def fetch_all_klines_from_2021(interval="1h"):
    all_data = []
    start_time = int(datetime(2021, 1, 1).timestamp() * 1000)
    now = int(datetime.now().timestamp() * 1000)

    while start_time < now:
        batch = fetch_klines_batch(start_time, now, interval)
        if not batch:
            break
        all_data.extend(batch)
        start_time = int(batch[-1]['time'].timestamp() * 1000) + 1
        time.sleep(0.4)  # hindari limit rate Binance
        if len(all_data) >= 5000:  # batasi agar tidak terlalu berat
            break
    return all_data

# Isi data awal
print("Mengambil data historis dari 2021...")
candles.extend(fetch_all_klines_from_2021(interval="1h"))
print(f"Total candle: {len(candles)}")

# WebSocket candle realtime
async def listen_binance_candles():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1h"
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

# WebSocket orderbook realtime
async def listen_binance_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

# Jalankan websocket di thread terpisah
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(listen_binance_candles())
    loop.create_task(listen_binance_orderbook())
    loop.run_forever()

# Mulai thread
t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Dash layout
app = dash.Dash(__name__)
app.title = "BTC Candlestick + Orderbook Realtime"

app.layout = html.Div([
    html.H3("Realtime BTC/USDT Candlestick Chart + Orderbook (Binance)"),
    dcc.Graph(id='btc-chart'),
    dcc.Interval(id='interval-update', interval=3000, n_intervals=0)
])

@app.callback(
    Output('btc-chart', 'figure'),
    Input('interval-update', 'n_intervals')
)
def update_chart(n):
    fig = go.Figure()

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

        # Garis horizontal orderbook (warna ungu, tebal sesuai volume)
        for price, volume in orderbook_data["bids"] + orderbook_data["asks"]:
            fig.add_shape(
                type="line",
                x0=df['time'].iloc[0],
                x1=df['time'].iloc[-1],
                y0=price,
                y1=price,
                line=dict(color="purple", width=min(volume * 2, 10)),
                xref='x', yref='y'
            )

        fig.update_layout(
            yaxis_title='Price',
            xaxis_title='Time',
            height=600,
            xaxis_rangeslider_visible=True,
            dragmode='zoom'
        )

    return fig

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)

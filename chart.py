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
from datetime import datetime, timedelta

# Data global
orderbook_data = {"bids": [], "asks": []}
candles = deque(maxlen=30)

# Tambahkan dummy candle biar tidak blank saat awal
now = datetime.now()
for i in range(30):
    time = now - timedelta(hours=29 - i)
    candles.append({
        'time': time,
        'open': 30000,
        'high': 30500,
        'low': 29500,
        'close': 30200
    })

# WebSocket Binance
async def listen_binance():
    uri_kline = "wss://stream.binance.com:9443/ws/btcusdt@kline_1h"
    uri_depth = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri_kline) as ws_kline, websockets.connect(uri_depth) as ws_depth:
        while True:
            done, _ = await asyncio.wait([
                ws_kline.recv(), ws_depth.recv()
            ], return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                data = json.loads(task.result())

                if 'k' in data:
                    k = data['k']
                    ts = datetime.fromtimestamp(k['t'] / 1000)
                    candles.append({
                        'time': ts,
                        'open': float(k['o']),
                        'high': float(k['h']),
                        'low': float(k['l']),
                        'close': float(k['c'])
                    })
                elif 'bids' in data:
                    orderbook_data["bids"] = [(float(p), float(v)) for p, v in data["bids"]]
                    orderbook_data["asks"] = [(float(p), float(v)) for p, v in data["asks"]]

# Jalankan WebSocket
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_binance())

t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Dash App
app = dash.Dash(__name__)
app.title = "Realtime BTC/USDT"
app.layout = html.Div(style={'backgroundColor': '#1e1e1e', 'padding': '10px'}, children=[
    html.H3("BTC/USDT 1H Realtime + Orderbook", style={'color': 'white'}),
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
            name="Candle",
            increasing_line_color='lime',
            decreasing_line_color='red'
        ))

        # Tambah garis horizontal untuk orderbook
        for price, _ in orderbook_data.get("bids", []) + orderbook_data.get("asks", []):
            fig.add_shape(
                type="line",
                x0=df['time'].iloc[0],
                x1=df['time'].iloc[-1],
                y0=price,
                y1=price,
                line=dict(color="white", width=0.8),
                xref='x', yref='y'
            )

        fig.update_layout(
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            height=700,
            margin=dict(l=50, r=50, t=50, b=40),
            xaxis_rangeslider_visible=False,
            xaxis=dict(title='Time'),
            yaxis=dict(title='Price')
        )

    return fig

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8050)

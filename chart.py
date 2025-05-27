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
candles = deque(maxlen=30)  # hanya simpan 30 candle terakhir (1 jam)

# WebSocket untuk candlestick 1 menit (dikumpulkan untuk time frame 1 jam)
async def listen_binance_candles():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    async with websockets.connect(uri) as websocket:
        temp_candles = []
        current_hour = None
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            k = parsed['k']
            ts = datetime.fromtimestamp(k['t'] / 1000)
            hour = ts.replace(minute=0, second=0, microsecond=0)

            if current_hour is None:
                current_hour = hour

            if hour != current_hour:
                df = pd.DataFrame(temp_candles)
                if not df.empty:
                    candles.append({
                        'time': current_hour,
                        'open': df['open'].iloc[0],
                        'high': df['high'].max(),
                        'low': df['low'].min(),
                        'close': df['close'].iloc[-1]
                    })
                temp_candles = []
                current_hour = hour

            temp_candles.append({
                'open': float(k['o']),
                'high': float(k['h']),
                'low': float(k['l']),
                'close': float(k['c']),
            })

# WebSocket untuk orderbook depth (level 20)
async def listen_binance_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

# Jalankan WebSocket di thread terpisah
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(listen_binance_candles())
    loop.create_task(listen_binance_orderbook())
    loop.run_forever()

t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Dash App
app = dash.Dash(__name__)
app.title = "Realtime BTC Chart"
app.layout = html.Div(style={'backgroundColor': '#1e1e1e', 'padding': '10px'}, children=[
    html.H3("BTC/USDT - 1 Hour Realtime Chart with Horizontal Orderbook", style={'color': 'white'}),
    dcc.Graph(id='btc-chart'),
    dcc.Interval(id='interval-update', interval=2000, n_intervals=0)
])

@app.callback(
    Output('btc-chart', 'figure'),
    Input('interval-update', 'n_intervals')
)
def update_chart(n):
    fig = go.Figure()

    # Candlestick
    if candles:
        df = pd.DataFrame(candles)
        fig.add_trace(go.Candlestick(
            x=df['time'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="BTC/USDT",
            increasing_line_color='green',
            decreasing_line_color='red'
        ))

        # Garis horizontal orderbook
        for price, _ in orderbook_data["bids"] + orderbook_data["asks"]:
            fig.add_shape(
                type="line",
                x0=df['time'].iloc[0],
                x1=df['time'].iloc[-1],
                y0=price,
                y1=price,
                line=dict(color="white", width=1),
                xref='x', yref='y'
            )

        fig.update_layout(
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            xaxis=dict(title='Time'),
            yaxis=dict(title='Price', tickformat=".2f"),
            height=700,
            xaxis_rangeslider_visible=False
        )
    return fig

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8050)

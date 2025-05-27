import dash
from dash import dcc, html
from dash.dependencies import Output, Input, State
import plotly.graph_objects as go
import asyncio
import threading
import websockets
import json
import pandas as pd
from collections import deque
from datetime import datetime, timedelta

# Global data storage
candles = deque(maxlen=200)
orderbook_data = {"bids": [], "asks": []}
selected_interval = "1m"

# WebSocket listeners
async def listen_candles(interval):
    uri = f"wss://stream.binance.com:9443/ws/btcusdt@kline_{interval}"
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

async def listen_orderbook():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as websocket:
        while True:
            data = await websocket.recv()
            parsed = json.loads(data)
            orderbook_data["bids"] = [(float(p), float(v)) for p, v in parsed.get("bids", [])]
            orderbook_data["asks"] = [(float(p), float(v)) for p, v in parsed.get("asks", [])]

def start_ws(interval):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(listen_candles(interval))
    loop.create_task(listen_orderbook())
    loop.run_forever()

# Start WebSocket in background thread
t = threading.Thread(target=start_ws, args=(selected_interval,))
t.daemon = True
t.start()

# Dash App Setup
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H3("Realtime BTC Candlestick + Orderbook Horizontal"),
    html.Div([
        html.Label("Select Time Frame:"),
        dcc.Dropdown(
            id='timeframe-selector',
            options=[
                {'label': '1 Minute', 'value': '1m'},
                {'label': '5 Minutes', 'value': '5m'},
                {'label': '1 Hour', 'value': '1h'}
            ],
            value='1m',
            clearable=False
        )
    ], style={'width': '200px'}),
    dcc.Graph(id='btc-chart'),
    dcc.Interval(id='interval-update', interval=2000, n_intervals=0)
])

@app.callback(
    Output('btc-chart', 'figure'),
    Input('interval-update', 'n_intervals'),
    State('timeframe-selector', 'value')
)
def update_chart(n, interval):
    global selected_interval
    if interval != selected_interval:
        selected_interval = interval

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

        last_x = df['time'].iloc[-1]
        offset = timedelta(minutes=5)

        for price, volume in orderbook_data["bids"] + orderbook_data["asks"]:
            fig.add_shape(
                type="line",
                x0=last_x - offset,
                x1=last_x,
                y0=price,
                y1=price,
                line=dict(color="purple", width=min(volume * 2, 10)),
                xref='x', yref='y'
            )

    fig.update_layout(
        xaxis_rangeslider_visible=True,
        dragmode='pan',
        hovermode='x unified',
        yaxis_title='Price',
        xaxis_title='Time',
        height=700,
        template='plotly_dark'
    )
    return fig

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import asyncio
import threading
import websockets
import json
import pandas as pd
from datetime import datetime

app = dash.Dash(__name__)

# Global data storage
candles = []
orderbook = {"bids": [], "asks": []}
last_candle_time = None
streaming = True

# WebSocket untuk candlestick 1m
async def ws_candles():
    global candles, last_candle_time
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    async with websockets.connect(uri) as ws:
        while True:
            data = await ws.recv()
            obj = json.loads(data)
            k = obj['k']
            t = datetime.fromtimestamp(k['t'] / 1000)
            if last_candle_time != t:
                candle = {
                    "time": t,
                    "open": float(k['o']),
                    "high": float(k['h']),
                    "low": float(k['l']),
                    "close": float(k['c']),
                }
                candles.append(candle)
                if len(candles) > 200:
                    candles.pop(0)
                last_candle_time = t

# WebSocket untuk orderbook depth
async def ws_orderbook():
    global orderbook
    uri = "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"
    async with websockets.connect(uri) as ws:
        while True:
            data = await ws.recv()
            obj = json.loads(data)
            orderbook["bids"] = [(float(p), float(v)) for p, v in obj.get("bids", [])]
            orderbook["asks"] = [(float(p), float(v)) for p, v in obj.get("asks", [])]

# Jalankan WebSocket di thread background
def start_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(ws_candles())
    loop.create_task(ws_orderbook())
    loop.run_forever()

t = threading.Thread(target=start_ws)
t.daemon = True
t.start()

# Layout Dash
app.layout = html.Div([
    html.H2("BTC/USDT Realtime Candlestick + Orderbook Horizontal"),
    dcc.Dropdown(
        id='timeframe',
        options=[
            {'label': '1 Minute', 'value': '1m'},
            {'label': '5 Minutes', 'value': '5m'},
            {'label': '15 Minutes', 'value': '15m'},
            {'label': '1 Hour', 'value': '1h'},
        ],
        value='1m',
        clearable=False,
        style={'width': '200px'}
    ),
    html.Button("Pause", id='pause-btn', n_clicks=0),
    dcc.Loading(dcc.Graph(id='chart'), type='circle'),
    dcc.Interval(id='interval', interval=3000, n_intervals=0),
    html.Div(id='status', style={'marginTop': 10})
])

@app.callback(
    Output('chart', 'figure'),
    Output('status', 'children'),
    Input('interval', 'n_intervals'),
    Input('timeframe', 'value'),
    Input('pause-btn', 'n_clicks'),
    State('pause-btn', 'children')
)
def update_chart(n, timeframe, n_clicks, pause_text):
    global streaming
    # Toggle pause/resume
    if n_clicks % 2 == 1:
        streaming = False
    else:
        streaming = True

    if not streaming:
        return dash.no_update, "Streaming paused."

    df = pd.DataFrame(candles)
    if df.empty:
        return go.Figure(), "Loading data..."

    # Resample candles sesuai timeframe
    if timeframe != '1m':
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        rule = timeframe.replace('m', 'T').replace('h', 'H')
        df = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna().reset_index()

    fig = go.Figure(data=[go.Candlestick(
        x=df['time'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name="BTC/USDT"
    )])

    # Orderbook: garis horizontal full x axis dengan ketebalan sesuai volume
    max_vol = max([v for p, v in orderbook['bids'] + orderbook['asks']] or [1])
    x0 = df['time'].iloc[0]
    x1 = df['time'].iloc[-1]

    for price, vol in orderbook['bids'] + orderbook['asks']:
        width = 1 + (vol / max_vol) * 8  # ketebalan max 9 px
        fig.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=price,
            y1=price,
            line=dict(color="purple", width=width),
            xref='x',
            yref='y'
        )

    fig.update_layout(
        height=700,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(title='Time', rangeslider=dict(visible=True), autorange=True),
        yaxis=dict(title='Price (USDT)', autorange=True),
        hovermode='closest',
    )
    return fig, "Streaming live data..."

@app.callback(
    Output('pause-btn', 'children'),
    Input('pause-btn', 'n_clicks'),
)
def toggle_pause_text(n):
    return "Resume" if n % 2 == 1 else "Pause"

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=8050)

#!/usr/bin/env python3
"""Paper Bot 10.0. No real orders, API keys or account access."""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

STATE = Path('state.json')
PAIRS = {'BTC':'XXBTZEUR', 'ETH':'XETHZEUR', 'SOL':'SOLEUR'}
FEE, CAP, STOP, DRAWDOWN, COOLDOWN = .001, .20, .06, .10, 3

def prices(pair):
    req = urllib.request.Request('https://api.kraken.com/0/public/OHLC?pair='+pair+'&interval=240',headers={'User-Agent':'PaperBot10/1.0'})
    with urllib.request.urlopen(req,timeout=25) as f: data=json.load(f)
    if data.get('error'): raise ValueError(str(data['error']))
    key=next(k for k in data['result'] if k!='last')
    # Last returned bar is unfinished. It must not influence a signal.
    return [(int(r[0]),float(r[4])) for r in data['result'][key][:-1]]

def sma(values,n): return sum(values[-n:])/n

def main():
    if STATE.exists(): state=json.loads(STATE.read_text())
    else: state={'cash_eur':1000.0,'positions':{},'peak_equity':1000.0,'last_bar':{},'last_exit_bar':{},'trades':[],'halted':False}
    markets={}
    for symbol,pair in PAIRS.items():
        try:
            series=prices(pair)
            if len(series)<52: raise ValueError('Not enough historical data')
            markets[symbol]=series
        except Exception as exc: print(symbol,'market data unavailable:',exc)
    if not markets: raise RuntimeError('No market prices available. Portfolio unchanged.')
    quotes={s:series[-1][1] for s,series in markets.items()}
    equity=state['cash_eur']+sum(p['qty']*quotes.get(s,p['entry']) for s,p in state['positions'].items())
    state['peak_equity']=max(state['peak_equity'],equity)
    if equity<=state['peak_equity']*(1-DRAWDOWN): state['halted']=True
    for symbol,series in markets.items():
        bar,price=series[-1]
        if bar<=state['last_bar'].get(symbol,0): continue
        state['last_bar'][symbol]=bar
        closes=[c for _,c in series]
        fast=sma(closes,20); slow=sma(closes,50)
        prevfast=sma(closes[:-1],20); prevslow=sma(closes[:-1],50)
        position=state['positions'].get(symbol)
        action='WAIT'
        if position and (price<=position['entry']*(1-STOP) or (prevfast>=prevslow and fast<slow) or state['halted']):
            received=position['qty']*price*(1-FEE)
            state['cash_eur']+=received
            state['trades'].append({'time':datetime.fromtimestamp(bar,timezone.utc).isoformat(),'symbol':symbol,'side':'SELL','price':price,'qty':position['qty'],'eur':round(received,6),'mode':'PAPER'})
            del state['positions'][symbol]
            state['last_exit_bar'][symbol]=bar
            action='PAPER SELL'
        elif not position and not state['halted'] and prevfast<=prevslow and fast>slow:
            last_exit=state['last_exit_bar'].get(symbol,0)
            if last_exit and bar-last_exit<COOLDOWN*14400: action='COOLDOWN'
            else:
                spend=min(state['cash_eur'],equity*CAP)
                if spend>=10:
                    qty=spend*(1-FEE)/price
                    state['cash_eur']-=spend
                    state['positions'][symbol]={'qty':qty,'entry':price,'spent_eur':spend}
                    state['trades'].append({'time':datetime.fromtimestamp(bar,timezone.utc).isoformat(),'symbol':symbol,'side':'BUY','price':price,'qty':qty,'eur':round(spend,6),'mode':'PAPER'})
                    action='PAPER BUY'
        print(f'{symbol} {price:.2f} EUR | SMA20={fast:.2f} SMA50={slow:.2f} | {action}')
    state['trades']=state['trades'][-500:]
    STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    current=state['cash_eur']+sum(p['qty']*quotes.get(s,p['entry']) for s,p in state['positions'].items())
    print(f'PAPER BOT 10.0 | virtual EUR {current:.2f} | cash EUR {state["cash_eur"]:.2f} | trades {len(state["trades"])} | halted {state["halted"]}')

if __name__=='__main__': main()

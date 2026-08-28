from flask import Flask, request, jsonify, render_template
from database import get_db, init_db, IS_POSTGRES
from sqlalchemy import text
import json
from datetime import datetime

app = Flask(__name__)
init_db()

def rows_to_dicts(result):
    keys = result.keys()
    return [dict(zip(keys, row)) for row in result.fetchall()]

def row_to_dict(result):
    keys = result.keys()
    row = result.fetchone()
    return dict(zip(keys, row)) if row else None

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/signals', methods=['GET'])
def get_signals():
    with get_db() as conn:
        result = conn.execute(text("SELECT * FROM signals WHERE status='pending' ORDER BY created_at DESC"))
        signals = rows_to_dicts(result)
    for s in signals:
        try: s['filters'] = json.loads(s.pop('filters_json') or '{}')
        except: s['filters'] = {}; s.pop('filters_json', None)
        for k, v in s.items():
            if hasattr(v, 'isoformat'): s[k] = str(v)
    return jsonify(signals)

@app.route('/api/signal', methods=['POST'])
def add_signal():
    data = request.get_json()
    if not data or 'match' not in data: return jsonify({'error': 'Missing match'}), 400
    fj = json.dumps(data.get('filters', {}))
    with get_db() as conn:
        if IS_POSTGRES:
            result = conn.execute(text('INSERT INTO signals (match,league,date,home_team,away_team,suggested_odds,kelly_stake,filters_json) VALUES (:m,:l,:d,:ht,:at,:so,:ks,:fj) RETURNING id'),
                {'m':data.get('match'),'l':data.get('league'),'d':data.get('date'),'ht':data.get('home_team'),'at':data.get('away_team'),'so':data.get('odds'),'ks':data.get('kelly_stake'),'fj':fj})
            sid = result.fetchone()[0]
        else:
            conn.execute(text('INSERT INTO signals (match,league,date,home_team,away_team,suggested_odds,kelly_stake,filters_json) VALUES (:m,:l,:d,:ht,:at,:so,:ks,:fj)'),
                {'m':data.get('match'),'l':data.get('league'),'d':data.get('date'),'ht':data.get('home_team'),'at':data.get('away_team'),'so':data.get('odds'),'ks':data.get('kelly_stake'),'fj':fj})
            result = conn.execute(text('SELECT last_insert_rowid()'))
            sid = result.scalar()
        conn.commit()
    return jsonify({'id': sid, 'status': 'pending'}), 201

@app.route('/api/bets', methods=['GET'])
def get_bets():
    q = 'SELECT * FROM bets WHERE 1=1'
    p = {}
    if request.args.get('status'): q += ' AND status=:s'; p['s'] = request.args['status']
    if request.args.get('league'): q += ' AND league=:l'; p['l'] = request.args['league']
    with get_db() as conn:
        result = conn.execute(text(q + ' ORDER BY created_at DESC'), p)
        bets = rows_to_dicts(result)
    for b in bets:
        for k,v in b.items():
            if hasattr(v,'isoformat'): b[k] = str(v)
    return jsonify(bets)

@app.route('/api/bets', methods=['POST'])
def create_bet():
    data = request.get_json()
    if not data or 'match' not in data: return jsonify({'error': 'Missing match'}), 400
    sid = data.get('signal_id')
    with get_db() as conn:
        if sid: conn.execute(text("UPDATE signals SET status='validated' WHERE id=:i"), {'i':sid})
        if IS_POSTGRES:
            result = conn.execute(text('INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES (:si,:m,:l,:d,:ht,:at,:so,:ao,:st,:bk) RETURNING id'),
                {'si':sid,'m':data.get('match'),'l':data.get('league'),'d':data.get('date'),'ht':data.get('home_team'),'at':data.get('away_team'),'so':data.get('suggested_odds'),'ao':data.get('actual_odds'),'st':data.get('stake'),'bk':data.get('bookmaker')})
            bid = result.fetchone()[0]
        else:
            conn.execute(text('INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES (:si,:m,:l,:d,:ht,:at,:so,:ao,:st,:bk)'),
                {'si':sid,'m':data.get('match'),'l':data.get('league'),'d':data.get('date'),'ht':data.get('home_team'),'at':data.get('away_team'),'so':data.get('suggested_odds'),'ao':data.get('actual_odds'),'st':data.get('stake'),'bk':data.get('bookmaker')})
            result = conn.execute(text('SELECT last_insert_rowid()'))
            bid = result.scalar()
        conn.commit()
    return jsonify({'id': bid, 'status': 'open'}), 201

@app.route('/api/bets/<int:bet_id>/result', methods=['PUT'])
def close_bet(bet_id):
    data = request.get_json()
    result_val = data.get('result') if data else None
    if result_val not in ('won','lost','void'): return jsonify({'error': 'Invalid result'}), 400
    with get_db() as conn:
        r = conn.execute(text('SELECT * FROM bets WHERE id=:i'), {'i':bet_id})
        bet = row_to_dict(r)
        if not bet: return jsonify({'error': 'Not found'}), 404
        stake = bet.get('stake') or 0; odds = bet.get('actual_odds') or 0
        profit = round(stake*(odds-1) if result_val=='won' else (-stake if result_val=='lost' else 0), 2)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(text('UPDATE bets SET status=:s,profit=:p,closed_at=:c WHERE id=:i'), {'s':result_val,'p':profit,'c':now,'i':bet_id})
        r2 = conn.execute(text('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1'))
        row = r2.fetchone()
        new_bk = round((row[0] if row else 1000)+profit, 2)
        conn.execute(text('INSERT INTO bankroll (amount,updated_at) VALUES (:a,:u)'), {'a':new_bk,'u':now})
        conn.commit()
    return jsonify({'id': bet_id, 'status': result_val, 'profit': profit})

@app.route('/api/signals/<int:sid>/ignore', methods=['PUT'])
def ignore_signal(sid):
    with get_db() as conn:
        conn.execute(text("UPDATE signals SET status='ignored' WHERE id=:i"), {'i':sid})
        conn.commit()
    return jsonify({'id': sid, 'status': 'ignored'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    with get_db() as conn:
        def sc(q): return conn.execute(text(q)).scalar() or 0
        total = sc("SELECT COUNT(*) FROM bets WHERE status!='open'")
        won = sc("SELECT COUNT(*) FROM bets WHERE status='won'")
        lost = sc("SELECT COUNT(*) FROM bets WHERE status='lost'")
        ob = sc("SELECT COUNT(*) FROM bets WHERE status='open'")
        tp = sc("SELECT COALESCE(SUM(profit),0) FROM bets WHERE status IN ('won','lost')")
        ts = sc("SELECT COALESCE(SUM(stake),0) FROM bets WHERE status IN ('won','lost')")
        r = conn.execute(text('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1')).fetchone()
        bk = r[0] if r else 1000
        hist_rows = conn.execute(text('SELECT amount,updated_at FROM bankroll ORDER BY updated_at ASC')).fetchall()
    return jsonify({'total_bets':total,'open_bets':ob,'won':won,'lost':lost,
        'win_rate':round(won/total*100,1) if total>0 else 0,
        'roi':round(tp/ts*100,1) if ts>0 else 0,
        'total_profit':round(float(tp),2),'total_staked':round(float(ts),2),
        'current_bankroll':round(float(bk),2),
        'bankroll_history':[{'amount':float(r[0]),'date':str(r[1])} for r in hist_rows]})

@app.route('/health')
def health():
    return jsonify({'status':'ok','db':'postgres' if IS_POSTGRES else 'sqlite'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

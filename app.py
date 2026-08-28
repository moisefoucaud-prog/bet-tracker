from flask import Flask, request, jsonify, render_template
import json, os
from datetime import datetime

app = Flask(__name__)

STARTUP_ERROR = None

try:
    from database import get_db, init_db, db
    init_db()
except Exception as e:
    STARTUP_ERROR = str(e)

@app.route('/health')
def health():
    if STARTUP_ERROR:
        return jsonify({'status': 'error', 'error': STARTUP_ERROR}), 500
    return jsonify({'status': 'ok', 'db': 'postgres' if os.environ.get('DATABASE_URL') else 'sqlite'})

@app.route('/')
def dashboard():
    if STARTUP_ERROR:
        return f'<h1>Startup Error</h1><pre>{STARTUP_ERROR}</pre>', 500
    return render_template('index.html')

@app.route('/api/signals', methods=['GET'])
def get_signals():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM signals WHERE status = 'pending' ORDER BY created_at DESC")
        signals = db.fetchall_dict(cur)
        cur.close(); conn.close()
        for s in signals:
            if s.get('filters_json'):
                try: s['filters'] = json.loads(s['filters_json'])
                except: s['filters'] = {}
            else: s['filters'] = {}
            s.pop('filters_json', None)
        return jsonify(signals)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/signal', methods=['POST'])
def add_signal():
    try:
        data = request.get_json()
        if not data or 'match' not in data:
            return jsonify({'error': 'Missing match'}), 400
        conn = get_db()
        cur = conn.cursor()
        p = db.placeholder()
        filters_json = json.dumps(data.get('filters', {}))
        if db.is_postgres:
            cur.execute(f'INSERT INTO signals (match,league,date,home_team,away_team,suggested_odds,kelly_stake,filters_json) VALUES ({p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id',
                (data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('odds'),data.get('kelly_stake'),filters_json))
            signal_id = cur.fetchone()[0]
        else:
            cur.execute(f'INSERT INTO signals (match,league,date,home_team,away_team,suggested_odds,kelly_stake,filters_json) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})',
                (data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('odds'),data.get('kelly_stake'),filters_json))
            cur.execute('SELECT last_insert_rowid()')
            signal_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return jsonify({'id': signal_id, 'status': 'pending'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bets', methods=['GET'])
def get_bets():
    try:
        conn = get_db()
        cur = conn.cursor()
        p = db.placeholder()
        query = 'SELECT * FROM bets WHERE 1=1'
        params = []
        if request.args.get('status'): query += f' AND status = {p}'; params.append(request.args.get('status'))
        if request.args.get('league'): query += f' AND league = {p}'; params.append(request.args.get('league'))
        cur.execute(query + ' ORDER BY created_at DESC', params)
        bets = db.fetchall_dict(cur)
        cur.close(); conn.close()
        return jsonify(bets)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bets', methods=['POST'])
def create_bet():
    try:
        data = request.get_json()
        if not data or 'match' not in data: return jsonify({'error': 'Missing match'}), 400
        conn = get_db(); cur = conn.cursor(); p = db.placeholder()
        signal_id = data.get('signal_id')
        if signal_id: cur.execute(f'UPDATE signals SET status={p} WHERE id={p}', ('validated', signal_id))
        if db.is_postgres:
            cur.execute(f'INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id',
                (signal_id,data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('suggested_odds'),data.get('actual_odds'),data.get('stake'),data.get('bookmaker')))
            bet_id = cur.fetchone()[0]
        else:
            cur.execute(f'INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p})',
                (signal_id,data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('suggested_odds'),data.get('actual_odds'),data.get('stake'),data.get('bookmaker')))
            cur.execute('SELECT last_insert_rowid()')
            bet_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return jsonify({'id': bet_id, 'status': 'open'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bets/<int:bet_id>/result', methods=['PUT'])
def close_bet(bet_id):
    try:
        data = request.get_json()
        result = data.get('result')
        if result not in ('won','lost','void'): return jsonify({'error': 'Invalid result'}), 400
        conn = get_db(); cur = conn.cursor(); p = db.placeholder()
        cur.execute(f'SELECT * FROM bets WHERE id={p}', (bet_id,))
        bet = db.fetchone_dict(cur)
        if not bet: return jsonify({'error': 'Not found'}), 404
        stake = bet.get('stake') or 0; odds = bet.get('actual_odds') or 0
        profit = round(stake*(odds-1) if result=='won' else (-stake if result=='lost' else 0), 2)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute(f'UPDATE bets SET status={p},profit={p},closed_at={p} WHERE id={p}', (result,profit,now,bet_id))
        cur.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1')
        row = db.fetchone_dict(cur)
        new_amount = round((row['amount'] if row else 1000)+profit, 2)
        cur.execute(f'INSERT INTO bankroll (amount,updated_at) VALUES ({p},{p})', (new_amount,now))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'id': bet_id, 'status': result, 'profit': profit})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/signals/<int:signal_id>/ignore', methods=['PUT'])
def ignore_signal(signal_id):
    try:
        conn = get_db(); cur = conn.cursor(); p = db.placeholder()
        cur.execute(f"UPDATE signals SET status={p} WHERE id={p}", ('ignored',signal_id))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'id': signal_id, 'status': 'ignored'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db(); cur = conn.cursor()
        def sc(q):
            cur.execute(q); r = cur.fetchone(); return r[0] if r else 0
        total = sc("SELECT COUNT(*) FROM bets WHERE status!='open'")
        won = sc("SELECT COUNT(*) FROM bets WHERE status='won'")
        lost = sc("SELECT COUNT(*) FROM bets WHERE status='lost'")
        ob = sc("SELECT COUNT(*) FROM bets WHERE status='open'")
        tp = sc("SELECT COALESCE(SUM(profit),0) FROM bets WHERE status IN ('won','lost')")
        ts = sc("SELECT COALESCE(SUM(stake),0) FROM bets WHERE status IN ('won','lost')")
        wr = round(won/total*100,1) if total>0 else 0
        roi = round(tp/ts*100,1) if ts>0 else 0
        cur.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1')
        row = db.fetchone_dict(cur)
        bk = row['amount'] if row else 1000
        cur.execute('SELECT amount,updated_at FROM bankroll ORDER BY updated_at ASC')
        hist = db.fetchall_dict(cur)
        cur.close(); conn.close()
        return jsonify({'total_bets':total,'open_bets':ob,'won':won,'lost':lost,'win_rate':wr,'roi':roi,'total_profit':round(tp,2),'total_staked':round(ts,2),'current_bankroll':round(bk,2),'bankroll_history':[{'amount':h['amount'],'date':str(h['updated_at'])} for h in hist]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

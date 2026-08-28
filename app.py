from flask import Flask, request, jsonify, render_template
from database import get_db
import json
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/signals', methods=['GET'])
def get_signals():
    conn = get_db()
    rows = conn.execute("SELECT * FROM signals WHERE status='pending' ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        try: row['filters'] = json.loads(row.pop('filters_json') or '{}')
        except: row['filters'] = {}; row.pop('filters_json', None)
        result.append(row)
    return jsonify(result)

@app.route('/api/signal', methods=['POST'])
def add_signal():
    data = request.get_json()
    if not data or 'match' not in data: return jsonify({'error': 'Missing match'}), 400
    conn = get_db()
    conn.execute('INSERT INTO signals (match,league,date,home_team,away_team,suggested_odds,kelly_stake,filters_json) VALUES (?,?,?,?,?,?,?,?)',
        (data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('odds'),data.get('kelly_stake'),json.dumps(data.get('filters', {}))))
    conn.commit()
    sid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return jsonify({'id': sid, 'status': 'pending'}), 201

@app.route('/api/bets', methods=['GET'])
def get_bets():
    conn = get_db()
    q = 'SELECT * FROM bets WHERE 1=1'
    p = []
    if request.args.get('status'): q += ' AND status=?'; p.append(request.args['status'])
    if request.args.get('league'): q += ' AND league=?'; p.append(request.args['league'])
    rows = conn.execute(q + ' ORDER BY created_at DESC', p).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/bets', methods=['POST'])
def create_bet():
    data = request.get_json()
    if not data or 'match' not in data: return jsonify({'error': 'Missing match'}), 400
    conn = get_db()
    sid = data.get('signal_id')
    if sid: conn.execute("UPDATE signals SET status='validated' WHERE id=?", (sid,))
    conn.execute('INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (sid,data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('suggested_odds'),data.get('actual_odds'),data.get('stake'),data.get('bookmaker')))
    conn.commit()
    bid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return jsonify({'id': bid, 'status': 'open'}), 201

@app.route('/api/bets/<int:bet_id>/result', methods=['PUT'])
def close_bet(bet_id):
    data = request.get_json()
    result = data.get('result') if data else None
    if result not in ('won','lost','void'): return jsonify({'error': 'Invalid result'}), 400
    conn = get_db()
    bet = dict(conn.execute('SELECT * FROM bets WHERE id=?', (bet_id,)).fetchone() or {})
    if not bet: conn.close(); return jsonify({'error': 'Not found'}), 404
    stake = bet.get('stake') or 0; odds = bet.get('actual_odds') or 0
    profit = round(stake*(odds-1) if result=='won' else (-stake if result=='lost' else 0), 2)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('UPDATE bets SET status=?,profit=?,closed_at=? WHERE id=?', (result,profit,now,bet_id))
    row = conn.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1').fetchone()
    conn.execute('INSERT INTO bankroll (amount,updated_at) VALUES (?,?)', (round((row['amount'] if row else 1000)+profit,2), now))
    conn.commit(); conn.close()
    return jsonify({'id': bet_id, 'status': result, 'profit': profit})

@app.route('/api/signals/<int:sid>/ignore', methods=['PUT'])
def ignore_signal(sid):
    conn = get_db()
    conn.execute("UPDATE signals SET status='ignored' WHERE id=?", (sid,))
    conn.commit(); conn.close()
    return jsonify({'id': sid, 'status': 'ignored'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    def sc(q): return conn.execute(q).fetchone()[0]
    total = sc("SELECT COUNT(*) FROM bets WHERE status!='open'")
    won = sc("SELECT COUNT(*) FROM bets WHERE status='won'")
    lost = sc("SELECT COUNT(*) FROM bets WHERE status='lost'")
    ob = sc("SELECT COUNT(*) FROM bets WHERE status='open'")
    tp = sc("SELECT COALESCE(SUM(profit),0) FROM bets WHERE status IN ('won','lost')")
    ts = sc("SELECT COALESCE(SUM(stake),0) FROM bets WHERE status IN ('won','lost')")
    row = conn.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1').fetchone()
    bk = row['amount'] if row else 1000
    hist = [{'amount':r['amount'],'date':r['updated_at']} for r in conn.execute('SELECT amount,updated_at FROM bankroll ORDER BY updated_at ASC').fetchall()]
    conn.close()
    return jsonify({'total_bets':total,'open_bets':ob,'won':won,'lost':lost,
        'win_rate':round(won/total*100,1) if total>0 else 0,
        'roi':round(tp/ts*100,1) if ts>0 else 0,
        'total_profit':round(tp,2),'total_staked':round(ts,2),
        'current_bankroll':round(bk,2),'bankroll_history':hist})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

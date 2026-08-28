from flask import Flask, request, jsonify, render_template
from database import get_db, init_db, db
import json
from datetime import datetime

app = Flask(__name__)

# Init DB tables at startup (Gunicorn-compatible)
init_db()

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/signals', methods=['GET'])
def get_signals():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM signals WHERE status = 'pending' ORDER BY created_at DESC")
    signals = db.fetchall_dict(cur)
    cur.close()
    conn.close()
    for s in signals:
        if s.get('filters_json'):
            try:
                s['filters'] = json.loads(s['filters_json'])
            except Exception:
                s['filters'] = {}
        else:
            s['filters'] = {}
        del s['filters_json']
    return jsonify(signals)

@app.route('/api/signal', methods=['POST'])
def add_signal():
    data = request.get_json()
    if not data or 'match' not in data:
        return jsonify({'error': 'Missing required field: match'}), 400
    conn = get_db()
    cur = conn.cursor()
    p = db.placeholder()
    filters_json = json.dumps(data.get('filters', {}))
    if db.is_postgres:
        cur.execute(f'INSERT INTO signals (match, league, date, home_team, away_team, suggested_odds, kelly_stake, filters_json) VALUES ({p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id',
            (data.get('match'), data.get('league'), data.get('date'), data.get('home_team'), data.get('away_team'), data.get('odds'), data.get('kelly_stake'), filters_json))
        signal_id = cur.fetchone()[0]
    else:
        cur.execute(f'INSERT INTO signals (match, league, date, home_team, away_team, suggested_odds, kelly_stake, filters_json) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})',
            (data.get('match'), data.get('league'), data.get('date'), data.get('home_team'), data.get('away_team'), data.get('odds'), data.get('kelly_stake'), filters_json))
        cur.execute('SELECT last_insert_rowid()')
        signal_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': signal_id, 'status': 'pending'}), 201

@app.route('/api/bets', methods=['GET'])
def get_bets():
    conn = get_db()
    cur = conn.cursor()
    status_filter = request.args.get('status')
    league_filter = request.args.get('league')
    p = db.placeholder()
    query = 'SELECT * FROM bets WHERE 1=1'
    params = []
    if status_filter:
        query += f' AND status = {p}'
        params.append(status_filter)
    if league_filter:
        query += f' AND league = {p}'
        params.append(league_filter)
    query += ' ORDER BY created_at DESC'
    cur.execute(query, params)
    bets = db.fetchall_dict(cur)
    cur.close()
    conn.close()
    return jsonify(bets)

@app.route('/api/bets', methods=['POST'])
def create_bet():
    data = request.get_json()
    if not data or 'match' not in data:
        return jsonify({'error': 'Missing required field: match'}), 400
    conn = get_db()
    cur = conn.cursor()
    p = db.placeholder()
    signal_id = data.get('signal_id')
    if signal_id:
        cur.execute(f'UPDATE signals SET status = {p} WHERE id = {p}', ('validated', signal_id))
    if db.is_postgres:
        cur.execute(f'INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id',
            (signal_id,data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('suggested_odds'),data.get('actual_odds'),data.get('stake'),data.get('bookmaker')))
        bet_id = cur.fetchone()[0]
    else:
        cur.execute(f'INSERT INTO bets (signal_id,match,league,date,home_team,away_team,suggested_odds,actual_odds,stake,bookmaker) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p})',
            (signal_id,data.get('match'),data.get('league'),data.get('date'),data.get('home_team'),data.get('away_team'),data.get('suggested_odds'),data.get('actual_odds'),data.get('stake'),data.get('bookmaker')))
        cur.execute('SELECT last_insert_rowid()')
        bet_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': bet_id, 'status': 'open'}), 201

@app.route('/api/bets/<int:bet_id>/result', methods=['PUT'])
def close_bet(bet_id):
    data = request.get_json()
    if not data or 'result' not in data:
        return jsonify({'error': 'Missing required field: result'}), 400
    result = data['result']
    if result not in ('won', 'lost', 'void'):
        return jsonify({'error': 'Result must be won, lost, or void'}), 400
    conn = get_db()
    cur = conn.cursor()
    p = db.placeholder()
    cur.execute(f'SELECT * FROM bets WHERE id = {p}', (bet_id,))
    bet = db.fetchone_dict(cur)
    if not bet:
        cur.close(); conn.close()
        return jsonify({'error': 'Bet not found'}), 404
    stake = bet.get('stake') or 0
    actual_odds = bet.get('actual_odds') or 0
    profit = round(stake*(actual_odds-1) if result=='won' else (-stake if result=='lost' else 0), 2)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute(f'UPDATE bets SET status={p},profit={p},closed_at={p} WHERE id={p}', (result,profit,now,bet_id))
    cur.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1')
    row = db.fetchone_dict(cur)
    new_amount = round((row['amount'] if row else 1000) + profit, 2)
    cur.execute(f'INSERT INTO bankroll (amount,updated_at) VALUES ({p},{p})', (new_amount,now))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'id': bet_id, 'status': result, 'profit': profit})

@app.route('/api/signals/<int:signal_id>/ignore', methods=['PUT'])
def ignore_signal(signal_id):
    conn = get_db()
    cur = conn.cursor()
    p = db.placeholder()
    cur.execute(f"UPDATE signals SET status={p} WHERE id={p}", ('ignored', signal_id))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'id': signal_id, 'status': 'ignored'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    cur = conn.cursor()
    def scalar(q, params=[]):
        cur.execute(q, params)
        row = cur.fetchone()
        return row[0] if row else 0
    total = scalar("SELECT COUNT(*) FROM bets WHERE status != 'open'")
    won = scalar("SELECT COUNT(*) FROM bets WHERE status = 'won'")
    lost = scalar("SELECT COUNT(*) FROM bets WHERE status = 'lost'")
    open_bets = scalar("SELECT COUNT(*) FROM bets WHERE status = 'open'")
    total_profit = scalar("SELECT COALESCE(SUM(profit),0) FROM bets WHERE status IN ('won','lost')")
    total_staked = scalar("SELECT COALESCE(SUM(stake),0) FROM bets WHERE status IN ('won','lost')")
    win_rate = round(won/total*100,1) if total>0 else 0
    roi = round(total_profit/total_staked*100,1) if total_staked>0 else 0
    cur.execute('SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1')
    row = db.fetchone_dict(cur)
    current_bankroll = row['amount'] if row else 1000
    cur.execute('SELECT amount,updated_at FROM bankroll ORDER BY updated_at ASC')
    history = db.fetchall_dict(cur)
    cur.close(); conn.close()
    return jsonify({'total_bets':total,'open_bets':open_bets,'won':won,'lost':lost,'win_rate':win_rate,'roi':roi,'total_profit':round(total_profit,2),'total_staked':round(total_staked,2),'current_bankroll':round(current_bankroll,2),'bankroll_history':[{'amount':h['amount'],'date':str(h['updated_at'])} for h in history]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

from flask import Flask, request, jsonify, render_template
from database import get_db, init_db, seed_demo_data
import json
from datetime import datetime

app = Flask(__name__)


@app.route('/')
def dashboard():
    return render_template('index.html')


@app.route('/api/signals', methods=['GET'])
def get_signals():
    conn = get_db()
    signals = conn.execute(
        "SELECT * FROM signals WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for s in signals:
        row = dict(s)
        if row.get('filters_json'):
            row['filters'] = json.loads(row['filters_json'])
        del row['filters_json']
        result.append(row)
    return jsonify(result)


@app.route('/api/signal', methods=['POST'])
def add_signal():
    data = request.get_json()
    if not data or 'match' not in data:
        return jsonify({"error": "Missing required field: match"}), 400

    conn = get_db()
    filters_json = json.dumps(data.get('filters', {}))
    conn.execute('''
        INSERT INTO signals (match, league, date, home_team, away_team, suggested_odds, kelly_stake, filters_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('match'),
        data.get('league'),
        data.get('date'),
        data.get('home_team'),
        data.get('away_team'),
        data.get('odds'),
        data.get('kelly_stake'),
        filters_json
    ))
    conn.commit()
    signal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({"id": signal_id, "status": "pending"}), 201


@app.route('/api/bets', methods=['GET'])
def get_bets():
    conn = get_db()
    status_filter = request.args.get('status')
    league_filter = request.args.get('league')

    query = "SELECT * FROM bets WHERE 1=1"
    params = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if league_filter:
        query += " AND league = ?"
        params.append(league_filter)

    query += " ORDER BY created_at DESC"
    bets = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(b) for b in bets])


@app.route('/api/bets', methods=['POST'])
def create_bet():
    data = request.get_json()
    if not data or 'match' not in data:
        return jsonify({"error": "Missing required field: match"}), 400

    conn = get_db()

    signal_id = data.get('signal_id')
    if signal_id:
        conn.execute("UPDATE signals SET status = 'validated' WHERE id = ?", (signal_id,))

    conn.execute('''
        INSERT INTO bets (signal_id, match, league, date, home_team, away_team,
            suggested_odds, actual_odds, stake, bookmaker)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        signal_id,
        data.get('match'),
        data.get('league'),
        data.get('date'),
        data.get('home_team'),
        data.get('away_team'),
        data.get('suggested_odds'),
        data.get('actual_odds'),
        data.get('stake'),
        data.get('bookmaker')
    ))
    conn.commit()
    bet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({"id": bet_id, "status": "open"}), 201


@app.route('/api/bets/<int:bet_id>/result', methods=['PUT'])
def close_bet(bet_id):
    data = request.get_json()
    if not data or 'result' not in data:
        return jsonify({"error": "Missing required field: result"}), 400

    result = data['result']
    if result not in ('won', 'lost', 'void'):
        return jsonify({"error": "Result must be won, lost, or void"}), 400

    conn = get_db()
    bet = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if not bet:
        conn.close()
        return jsonify({"error": "Bet not found"}), 404

    stake = bet['stake'] or 0
    actual_odds = bet['actual_odds'] or 0

    if result == 'won':
        profit = stake * (actual_odds - 1)
    elif result == 'lost':
        profit = -stake
    else:  # void
        profit = 0

    profit = round(profit, 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute('''
        UPDATE bets SET status = ?, profit = ?, closed_at = ? WHERE id = ?
    ''', (result, profit, now, bet_id))

    # Update bankroll
    current_bankroll = conn.execute(
        "SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1"
    ).fetchone()
    new_amount = round((current_bankroll['amount'] if current_bankroll else 1000) + profit, 2)
    conn.execute("INSERT INTO bankroll (amount, updated_at) VALUES (?, ?)", (new_amount, now))

    conn.commit()
    conn.close()
    return jsonify({"id": bet_id, "status": result, "profit": profit})


@app.route('/api/signals/<int:signal_id>/ignore', methods=['PUT'])
def ignore_signal(signal_id):
    conn = get_db()
    conn.execute("UPDATE signals SET status = 'ignored' WHERE id = ?", (signal_id,))
    conn.commit()
    conn.close()
    return jsonify({"id": signal_id, "status": "ignored"})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) as c FROM bets WHERE status != 'open'").fetchone()['c']
    won = conn.execute("SELECT COUNT(*) as c FROM bets WHERE status = 'won'").fetchone()['c']
    lost = conn.execute("SELECT COUNT(*) as c FROM bets WHERE status = 'lost'").fetchone()['c']
    open_bets = conn.execute("SELECT COUNT(*) as c FROM bets WHERE status = 'open'").fetchone()['c']

    total_profit = conn.execute(
        "SELECT COALESCE(SUM(profit), 0) as p FROM bets WHERE status IN ('won','lost')"
    ).fetchone()['p']
    total_staked = conn.execute(
        "SELECT COALESCE(SUM(stake), 0) as s FROM bets WHERE status IN ('won','lost')"
    ).fetchone()['s']

    win_rate = round((won / total * 100), 1) if total > 0 else 0
    roi = round((total_profit / total_staked * 100), 1) if total_staked > 0 else 0

    bankroll = conn.execute(
        "SELECT amount FROM bankroll ORDER BY id DESC LIMIT 1"
    ).fetchone()
    current_bankroll = bankroll['amount'] if bankroll else 1000

    # Bankroll history for chart
    history = conn.execute(
        "SELECT amount, updated_at FROM bankroll ORDER BY updated_at ASC"
    ).fetchall()

    conn.close()

    return jsonify({
        "total_bets": total,
        "open_bets": open_bets,
        "won": won,
        "lost": lost,
        "win_rate": win_rate,
        "roi": roi,
        "total_profit": round(total_profit, 2),
        "total_staked": round(total_staked, 2),
        "current_bankroll": round(current_bankroll, 2),
        "bankroll_history": [{"amount": h['amount'], "date": h['updated_at']} for h in history]
    })


if __name__ == '__main__':
    init_db()
    seed_demo_data()
    app.run(host='0.0.0.0', port=5001, debug=True)

"""User-owned cessation plans, cravings and explicit daily confirmations."""
import csv
import io
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from flask import g, jsonify, request
from .international import money
from .timezones import get_zone
from .push import queue_refresh

TRIGGERS = ('', 'coffee', 'stress', 'meal', 'social', 'boredom', 'other')
STRATEGIES = ('walk', 'water', 'breathe', 'distract')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS journeys (
 user_id INTEGER PRIMARY KEY REFERENCES users(id), document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
 user_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL, timezone TEXT NOT NULL,
 quantity INTEGER NOT NULL, confirmed_at TEXT NOT NULL,
 PRIMARY KEY(user_id,day,timezone)
);
CREATE TABLE IF NOT EXISTS cravings (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 started_at TEXT NOT NULL, pause_until TEXT NOT NULL, trigger TEXT NOT NULL,
 strategy TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT 'pending', resolved_at TEXT,
 cigarette_id INTEGER REFERENCES cigarettes(id) ON DELETE SET NULL,
 idempotency_key TEXT NOT NULL, UNIQUE(user_id,idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS cravings_pending ON cravings(user_id) WHERE outcome='pending';
CREATE INDEX IF NOT EXISTS cravings_user_date ON cravings(user_id,started_at);
'''


def defaults():
    return dict(version=0, mode='observe', quit_date=None, reason='', strategy='walk',
                steps=[], country='other', baseline=None, daily_enabled=False, daily_time='09:00',
                weekly_enabled=False, weekly_day=0, weekly_time='10:00', quiet_start='22:00', quiet_end='08:00')


def plan_for(conn, user_id):
    row = conn.execute('SELECT document FROM journeys WHERE user_id=?', (user_id,)).fetchone()
    return {**defaults(), **json.loads(row[0])} if row else defaults()


def reminder_preferences(conn, user_id):
    plan = plan_for(conn, user_id)
    return {key: plan[key] for key in ('daily_enabled', 'daily_time', 'weekly_enabled', 'weekly_day', 'weekly_time', 'quiet_start', 'quiet_end')}


def invalidate_checkins(conn, user_id, occurred_at):
    instant = datetime.fromisoformat(occurred_at)
    zones = conn.execute('SELECT DISTINCT timezone FROM checkins WHERE user_id=?', (user_id,)).fetchall()
    for row in zones:
        day = instant.astimezone(get_zone(row[0])).date().isoformat()
        conn.execute('DELETE FROM checkins WHERE user_id=? AND day=? AND timezone=?', (user_id, day, row[0]))


def goal_for(user, plan, day):
    if plan['mode']=='observe':return None
    value=user['daily_target']
    for step in plan['steps']:
        if step['date']<=day:value=step['goal']
    if plan['mode']=='quit' and plan['quit_date'] and day>=plan['quit_date']:value=0
    return value


def register_routes(app, db, now, stamp, body, fail, integer, bounds, entries):
    def parse_day(value):
        try:
            parsed = date.fromisoformat(value)
            if parsed.year < 2000 or parsed.isoformat() != value:
                raise ValueError()
            return parsed
        except (TypeError, ValueError):
            fail('invalid_entry_date')

    def local_today():
        return now().astimezone(get_zone(g.user['timezone'])).date()

    def save(plan):
        plan['version'] += 1
        db().execute('INSERT INTO journeys VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET document=excluded.document',
                     (g.user['id'], json.dumps(plan)))
        queue_refresh(db(), g.user['id'])

    def goal(plan,day):
        return goal_for(g.user,plan,day)

    def daily(start, end):
        tz = get_zone(g.user['timezone'])
        days = {(start+timedelta(days=i)).isoformat(): dict(quantity=0, amounts={}, confirmed=False)
                for i in range((end-start).days+1)}
        for row in entries(start, end, tz):
            day = datetime.fromisoformat(row['occurred_at']).astimezone(tz).date().isoformat()
            item = days[day]
            item['quantity'] += row['quantity']
            item['amounts'][row['currency']] = item['amounts'].get(row['currency'], 0)+row['quantity']*row['unit_cost_micros']
        for row in db().execute('SELECT * FROM checkins WHERE user_id=? AND timezone=? AND day>=? AND day<=?',
                                (g.user['id'], g.user['timezone'], start.isoformat(), end.isoformat())):
            days[row['day']]['confirmed'] = row['quantity'] == days[row['day']]['quantity']
        return days

    @app.get('/api/coaching')
    def overview():
        today = local_today()
        plan = plan_for(db(), g.user['id'])
        days = daily(today-timedelta(days=30), today)
        weeks = []
        for offset in (7, 14):
            subset = [days[(today-timedelta(days=i)).isoformat()] for i in range(offset-6, offset+1)]
            weeks.append(dict(quantity=sum(d['quantity'] for d in subset),
                              confirmed_days=sum(d['confirmed'] for d in subset),
                              costs={code: money(sum(d['amounts'].get(code, 0) for d in subset), code)
                                     for code in {c for d in subset for c in d['amounts']}}))
        progress = None
        baseline = plan['baseline']
        if baseline:
            start = date.fromisoformat(baseline['end'])+timedelta(days=1)
            # Only explicitly confirmed, completed days contribute to progress.
            confirmed = [d for d in daily(start,today-timedelta(days=1)).values() if d['confirmed']] if start<today else []
            n = len(confirmed)
            quantity = sum(d['quantity'] for d in confirmed)
            reference = Decimal(baseline['quantity'])/baseline['days']
            amounts = {c: sum(d['amounts'].get(c, 0) for d in confirmed) for c in {c for d in confirmed for c in d['amounts']}}
            # Different currencies cannot establish savings against a fixed reference.
            comparable = set(amounts).issubset(baseline['amounts'])
            progress = dict(confirmed_days=n, average=round(quantity/n, 2) if n else None,
                            reference_average=round(float(reference), 2),
                            quantity_difference=round(float(reference*n-quantity), 2) if n else None,
                            reduction_percent=round(float((reference-Decimal(quantity)/n)*100/reference), 2) if n and reference else None,
                            estimated_cost_difference={c: money(Decimal(v)*n/baseline['days']-amounts.get(c, 0), c)
                                                       for c, v in baseline['amounts'].items()} if n and comparable else {})
        confirmed_zero = db().execute('SELECT COUNT(*) FROM checkins WHERE user_id=? AND timezone=? AND day<? AND quantity=0',
                                     (g.user['id'], g.user['timezone'], today.isoformat())).fetchone()[0]
        passed = db().execute("SELECT COUNT(*) FROM cravings WHERE user_id=? AND outcome='passed'", (g.user['id'],)).fetchone()[0]
        last = db().execute('SELECT MAX(occurred_at) FROM cigarettes WHERE user_id=?', (g.user['id'],)).fetchone()[0]
        quit_since = None
        if plan['mode'] == 'quit' and plan['quit_date'] and plan['quit_date'] <= today.isoformat():
            quit_since = stamp(datetime.combine(date.fromisoformat(plan['quit_date']), time.min, get_zone(g.user['timezone'])))
            if last and last > quit_since:
                quit_since = last
        pending = db().execute("SELECT * FROM cravings WHERE user_id=? AND outcome='pending'", (g.user['id'],)).fetchone()
        low, high = bounds(today-timedelta(days=29), today, get_zone(g.user['timezone']))
        trigger_counts = []
        for trigger in TRIGGERS[1:]:
            c = db().execute('SELECT COALESCE(SUM(quantity),0) FROM cigarettes WHERE user_id=? AND trigger=? AND occurred_at>=? AND occurred_at<?',
                             (g.user['id'], trigger, low, high)).fetchone()[0]
            r = db().execute("SELECT COUNT(*),COALESCE(SUM(CASE WHEN outcome='passed' THEN 1 ELSE 0 END),0) FROM cravings WHERE user_id=? AND trigger=? AND started_at>=? AND started_at<?",
                             (g.user['id'], trigger, low, high)).fetchone()
            trigger_counts.append(dict(trigger=trigger, cigarettes=c, cravings=r[0], passed=r[1]))
        return jsonify(plan={**plan, 'daily_goal': g.user['daily_target']}, current_goal=goal(plan, today.isoformat()),
                       now=stamp(now()), timezone=g.user['timezone'], local_today=today.isoformat(),
                       local_datetime=now().astimezone(get_zone(g.user['timezone'])).isoformat(),
                       days=[dict(date=d, quantity=v['quantity'], confirmed=v['confirmed'], goal=goal(plan,d),
                                  costs={c: money(a,c) for c,a in v['amounts'].items()}) for d,v in days.items()],
                       weekly=dict(start=(today-timedelta(days=7)).isoformat(), end=(today-timedelta(days=1)).isoformat(),
                                   current=weeks[0], previous=weeks[1]), progress=progress,
                       confirmed_smoke_free_days=confirmed_zero, cravings_passed=passed, quit_since=quit_since,
                       pending_craving=dict(pending) if pending else None, triggers=trigger_counts)

    @app.put('/api/coaching/plan')
    def update_plan():
        data = body()
        with db():
            db().execute('BEGIN IMMEDIATE')
            plan = plan_for(db(), g.user['id'])
            if type(data.get('version')) is not int or data['version'] != plan['version']:
                fail('plan_conflict', 409)
            for field, choices in [('mode', ('observe','reduce','quit')), ('strategy', STRATEGIES), ('country', ('other','FR','GB','JP'))]:
                if field in data:
                    if data[field] not in choices:
                        fail('invalid_input')
                    plan[field] = data[field]
            if 'reason' in data:
                if not isinstance(data['reason'], str) or len(data['reason'])>300:
                    fail('invalid_input')
                plan['reason'] = data['reason'].strip()
            if 'quit_date' in data:
                plan['quit_date'] = None if data['quit_date'] in (None,'') else parse_day(data['quit_date']).isoformat()
            if 'daily_goal' in data:
                value = integer(data['daily_goal'],0,200,'daily_target')
                db().execute('UPDATE users SET daily_target=? WHERE id=?',(value,g.user['id']))
            if 'steps' in data:
                if not isinstance(data['steps'],list) or len(data['steps'])>30:
                    fail('invalid_input')
                steps=[]
                for step in data['steps']:
                    if not isinstance(step,dict):fail('invalid_input')
                    steps.append(dict(date=parse_day(step.get('date')).isoformat(),goal=integer(step.get('goal'),0,200,'daily_target')))
                if len({s['date'] for s in steps})!=len(steps):fail('invalid_input')
                plan['steps']=sorted(steps,key=lambda s:s['date'])
            for key in ('daily_enabled','weekly_enabled'):
                if key in data:
                    if type(data[key]) is not bool:fail('invalid_input')
                    plan[key]=data[key]
            for key in ('daily_time','weekly_time','quiet_start','quiet_end'):
                if key in data:
                    if not isinstance(data[key],str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',data[key]):fail('invalid_input')
                    plan[key]=data[key]
            if 'weekly_day' in data:plan['weekly_day']=integer(data['weekly_day'],0,6,'day')
            for kind in ('daily','weekly'):
                at,a,b=plan[kind+'_time'],plan['quiet_start'],plan['quiet_end']
                quiet=(a<=at<b) if a<b else (at>=a or at<b) if a>b else False
                if plan[kind+'_enabled'] and quiet:fail('reminder_quiet_conflict')
            save(plan)
        return jsonify(version=plan['version'])

    @app.post('/api/coaching/baseline')
    def freeze_baseline():
        data=body();start=parse_day(data.get('start'));end=parse_day(data.get('end'))
        if start>end or (end-start).days>=90 or end>=local_today():fail('invalid_period')
        with db():
            db().execute('BEGIN IMMEDIATE')
            plan=plan_for(db(),g.user['id'])
            if plan['baseline']:fail('baseline_exists',409)
            values=list(daily(start,end).values())
            quantity=sum(d['quantity'] for d in values)
            if not quantity:fail('baseline_empty')
            plan['baseline']=dict(start=start.isoformat(),end=end.isoformat(),days=len(values),quantity=quantity,
                                  timezone=g.user['timezone'],
                                  amounts={c:sum(d['amounts'].get(c,0) for d in values) for c in {c for d in values for c in d['amounts']}})
            save(plan)
        return jsonify(plan['baseline']),201

    @app.put('/api/check-ins/<day>')
    def confirm(day):
        parsed=parse_day(day);data=body()
        if parsed>local_today():fail('invalid_entry_date')
        expected=integer(data.get('quantity'),0,1000000,'quantity')
        with db():
            db().execute('BEGIN IMMEDIATE')
            actual=daily(parsed,parsed)[day]['quantity']
            if expected!=actual:fail('checkin_conflict',409)
            db().execute('INSERT INTO checkins VALUES(?,?,?,?,?) ON CONFLICT(user_id,day,timezone) DO UPDATE SET quantity=excluded.quantity,confirmed_at=excluded.confirmed_at',
                         (g.user['id'],day,g.user['timezone'],actual,stamp(now())))
            queue_refresh(db(),g.user['id'])
        return jsonify(date=day,quantity=actual,confirmed=True)

    @app.delete('/api/check-ins/<day>')
    def unconfirm(day):
        parse_day(day)
        with db():
            db().execute('DELETE FROM checkins WHERE user_id=? AND day=? AND timezone=?',(g.user['id'],day,g.user['timezone']))
            queue_refresh(db(),g.user['id'])
        return '',204

    @app.post('/api/cravings')
    def start_craving():
        data=body();key=request.headers.get('Idempotency-Key','')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',key):fail('invalid_idempotency')
        trigger=data.get('trigger','');strategy=data.get('strategy','walk')
        if trigger not in TRIGGERS or strategy not in STRATEGIES:fail('invalid_input')
        minutes=integer(data.get('minutes',3),1,15,'pause_minutes')
        with db():
            db().execute('BEGIN IMMEDIATE')
            existing=db().execute('SELECT * FROM cravings WHERE user_id=? AND idempotency_key=?',(g.user['id'],key)).fetchone()
            if not existing:existing=db().execute("SELECT * FROM cravings WHERE user_id=? AND outcome='pending'",(g.user['id'],)).fetchone()
            if existing:return jsonify(dict(existing)),200
            instant=now()
            cursor=db().execute('INSERT INTO cravings(user_id,started_at,pause_until,trigger,strategy,idempotency_key) VALUES(?,?,?,?,?,?) RETURNING id',
                                (g.user['id'],stamp(instant),stamp(instant+timedelta(minutes=minutes)),trigger,strategy,key))
            queue_refresh(db(),g.user['id'])
            row=db().execute('SELECT * FROM cravings WHERE id=?',(cursor.fetchone()[0],)).fetchone()
        return jsonify(dict(row)),201

    @app.put('/api/cravings/<int:craving_id>')
    def finish_craving(craving_id):
        outcome=body().get('outcome')
        if outcome not in ('passed','smoked','cancelled'):fail('invalid_input')
        with db():
            db().execute('BEGIN IMMEDIATE')
            row=db().execute('SELECT * FROM cravings WHERE id=? AND user_id=?',(craving_id,g.user['id'])).fetchone()
            if not row:fail('not_found',404)
            if row['outcome']!='pending':
                if row['outcome']!=outcome:fail('craving_conflict',409)
                return jsonify(dict(row))
            instant=stamp(now());entry=None
            if outcome=='smoked':
                unit=int((Decimal(g.user['pack_price_micros'])/g.user['pack_size']).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                cursor=db().execute('INSERT INTO cigarettes(user_id,occurred_at,quantity,unit_cost_micros,source,currency,trigger) VALUES(?,?,1,?,?,?,?) RETURNING id',
                                    (g.user['id'],instant,unit,'api',g.user['currency'],row['trigger']))
                entry=cursor.fetchone()[0];invalidate_checkins(db(),g.user['id'],instant)
            db().execute('UPDATE cravings SET outcome=?,resolved_at=?,cigarette_id=? WHERE id=?',(outcome,instant,entry,craving_id))
            queue_refresh(db(),g.user['id'])
            row=db().execute('SELECT * FROM cravings WHERE id=?',(craving_id,)).fetchone()
        return jsonify(dict(row))

    @app.patch('/api/cigarettes/<int:entry_id>/context')
    def context(entry_id):
        trigger=body().get('trigger','')
        if trigger not in TRIGGERS:fail('invalid_input')
        with db():
            changed=db().execute('UPDATE cigarettes SET trigger=? WHERE id=? AND user_id=?',(trigger,entry_id,g.user['id'])).rowcount
            if not changed:fail('not_found',404)
            queue_refresh(db(),g.user['id'])
        return jsonify(trigger=trigger)

    @app.get('/api/coaching/export.csv')
    def coaching_export():
        today=local_today();plan=plan_for(db(),g.user['id']);output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['date','timezone','quantity','confirmed','chosen_goal','historical_costs'])
        for day, item in daily(today-timedelta(days=30),today-timedelta(days=1)).items():
            amounts='; '.join(f'{code} {money(amount,code)}' for code,amount in sorted(item['amounts'].items()))
            writer.writerow([day,g.user['timezone'],item['quantity'],str(item['confirmed']).lower(),goal(plan,day),amounts])
        return app.response_class('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=suuless-progress.csv'})

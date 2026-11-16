"""Pure calculation for the segment (study-hours) scheme.

Rules (see README 计算口径):
- Inputs are numbered study periods with explicit start/end and timezone.
- Periods of the same learner are merged by union on the Shanghai timeline;
  overlaps and touching intervals count once, with source codes kept as evidence.
- Merged intervals are split at Shanghai ISO-week (Mon 00:00) and month (1st 00:00)
  boundaries, so cross-week / cross-month time is never double counted.
- A week counts as a return visit only when merged study time >= 30 minutes.
- A learner's cohort week is the FIRST week that reaches the threshold.
All math runs on raw seconds; minutes are derived (rounded to 1 decimal) for display/storage.
"""
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import hashlib, json

TZ = ZoneInfo('Asia/Shanghai')
WEEK_THRESHOLD_SECONDS = 30 * 60
MONTH_CAP_MINUTES = 600.0


def parse_ts(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('时段时间必须带时区')
    return d.astimezone(TZ)


def monday(day):
    return day - timedelta(days=day.weekday())


def week_bounds(day):
    start = datetime.combine(monday(day), datetime.min.time(), TZ)
    return start, start + timedelta(days=7)


def month_start(day):
    return datetime(day.year, day.month, 1, tzinfo=TZ)


def next_month_start(day):
    if day.month == 12:
        return datetime(day.year + 1, 1, 1, tzinfo=TZ)
    return datetime(day.year, day.month + 1, 1, tzinfo=TZ)


def period_key(day):
    return f'{day.year:04d}-{day.month:02d}'


def merge_intervals(segments):
    """Union of one learner's segments. Returns ordered non-overlapping intervals.

    Each interval: {start, end, sources:[codes], minutes}. Touching intervals merge.
    """
    raw = []
    for seg in segments:
        start = parse_ts(seg['started_at'])
        end = parse_ts(seg['ended_at'])
        if end <= start:
            raise ValueError(f"时段 {seg['code']} 的结束必须晚于开始")
        raw.append((start, end, seg['code']))
    raw.sort(key=lambda x: (x[0], x[1]))
    merged = []
    for start, end, code in raw:
        if merged and start <= merged[-1]['end']:
            cur = merged[-1]
            if end > cur['end']:
                cur['end'] = end
            cur['sources'].append(code)
        else:
            merged.append({'start': start, 'end': end, 'sources': [code]})
    for itv in merged:
        itv['minutes'] = round((itv['end'] - itv['start']).total_seconds() / 60.0, 1)
    return merged


def split_at(interval, cuts):
    """Split one merged interval at boundary datetimes strictly inside it."""
    start, end = interval['start'], interval['end']
    points = [start] + [c for c in cuts if start < c < end] + [end]
    pieces = []
    for a, b in zip(points, points[1:]):
        if b > a:
            pieces.append({'start': a, 'end': b,
                           'seconds': (b - a).total_seconds(),
                           'sources': list(interval['sources'])})
    return pieces


def weekly_pieces(merged):
    """Split merged intervals at every ISO Monday boundary they cross."""
    cuts = set()
    for itv in merged:
        cur = week_bounds(itv['start'].date())[1]
        while cur < itv['end']:
            cuts.add(cur)
            cur += timedelta(days=7)
    pieces = []
    for itv in merged:
        pieces.extend(split_at(itv, sorted(cuts)))
    return pieces


def monthly_pieces(merged):
    """Split merged intervals at every 1st-of-month boundary they cross."""
    cuts = set()
    for itv in merged:
        cur = next_month_start(itv['start'].date())
        while cur < itv['end']:
            cuts.add(cur)
            cur = next_month_start(cur.date())
    pieces = []
    for itv in merged:
        pieces.extend(split_at(itv, sorted(cuts)))
    return pieces


def aggregate_weeks(merged):
    """week_monday_date -> {seconds, minutes, qualified, pieces}."""
    agg = defaultdict(lambda: {'seconds': 0.0, 'pieces': []})
    for p in weekly_pieces(merged):
        key = monday(p['start'].date())
        agg[key]['seconds'] += p['seconds']
        agg[key]['pieces'].append(p)
    out = {}
    for key, val in agg.items():
        minutes = round(val['seconds'] / 60.0, 1)
        out[key.isoformat()] = {'week': key.isoformat(),
                                'seconds': round(val['seconds'], 1),
                                'minutes': minutes,
                                'qualified': val['seconds'] >= WEEK_THRESHOLD_SECONDS,
                                'pieces': [{'start': p['start'].isoformat(),
                                            'end': p['end'].isoformat(),
                                            'minutes': round(p['seconds'] / 60.0, 1),
                                            'sources': p['sources']} for p in val['pieces']]}
    return out


def aggregate_months(merged):
    """period 'YYYY-MM' -> {seconds, minutes, pieces} (raw, before cap)."""
    agg = defaultdict(lambda: {'seconds': 0.0, 'pieces': []})
    for p in monthly_pieces(merged):
        key = period_key(p['start'].date())
        agg[key]['seconds'] += p['seconds']
        agg[key]['pieces'].append(p)
    out = {}
    for key, val in agg.items():
        out[key] = {'period': key,
                    'seconds': round(val['seconds'], 1),
                    'minutes': round(val['seconds'] / 60.0, 1),
                    'pieces': [{'start': p['start'].isoformat(),
                                'end': p['end'].isoformat(),
                                'minutes': round(p['seconds'] / 60.0, 1),
                                'sources': p['sources']} for p in val['pieces']]}
    return out


def cap_minutes(raw_minutes):
    return min(round(float(raw_minutes), 1), MONTH_CAP_MINUTES)


def calculate(snapshot):
    """Segment-scheme cohort calculation from a frozen snapshot."""
    cfg = snapshot['config']
    as_of = date.fromisoformat(cfg['as_of'])
    start = date.fromisoformat(cfg['start_week'])
    end = date.fromisoformat(cfg['end_week'])
    horizon = cfg['horizon']
    cutoff = datetime.combine(as_of + timedelta(days=1), datetime.min.time(), TZ)
    by_learner = defaultdict(list)
    future = 0
    for seg in snapshot['segments']:
        end_ts = parse_ts(seg['ended_at'])
        if end_ts > cutoff:
            future += 1
            continue
        by_learner[seg['learner']].append(seg)
    if not by_learner:
        raise ValueError('截至日以前没有有效学习时段，请核对时间和导入')
    learner_weeks = {}
    learner_months = {}
    learner_merges = {}
    first_qualified = {}
    for learner, segs in by_learner.items():
        merged = merge_intervals(segs)
        learner_merges[learner] = merged
        weeks = aggregate_weeks(merged)
        learner_weeks[learner] = weeks
        learner_months[learner] = aggregate_months(merged)
        qualified = sorted(w for w, d in weeks.items() if d['qualified'])
        if qualified:
            first_qualified[learner] = date.fromisoformat(qualified[0])
    if not first_qualified:
        raise ValueError('没有任何学员单周合并学时达到30分钟，无法建立回访队列')
    cohorts = defaultdict(list)
    for learner, wk in first_qualified.items():
        if start <= wk <= end:
            cohorts[wk].append(learner)
    if not cohorts:
        raise ValueError('所选首次达标周没有队列；窗口前已达标学员不会重新分配')
    rows = []
    for wk in sorted(cohorts):
        members = sorted(cohorts[wk])
        cells = []
        for i in range(horizon + 1):
            target = wk + timedelta(weeks=i)
            mature = target + timedelta(days=6) <= as_of
            tkey = target.isoformat()
            active = sorted(m for m in members
                            if tkey in learner_weeks[m] and learner_weeks[m][tkey]['qualified'])
            cells.append({
                'week_index': i,
                'target_week': tkey,
                'mature': mature,
                'active': len(active) if mature else None,
                'rate': len(active) / len(members) if mature else None,
                'visited': active if mature else [],
                'missing': [m for m in members if m not in active] if mature else [],
                'minutes': {m: learner_weeks[m][tkey]['minutes']
                            for m in members if tkey in learner_weeks[m]} if mature else {},
            })
        rows.append({'cohort_week': wk.isoformat(),
                     'iso_label': f'{wk.isocalendar().year}-W{wk.isocalendar().week:02}',
                     'size': len(members), 'members': members, 'cells': cells})
    evidence = {learner: [{'start': itv['start'].isoformat(), 'end': itv['end'].isoformat(),
                           'minutes': itv['minutes'], 'sources': itv['sources']}
                          for itv in merged]
                for learner, merged in learner_merges.items()}
    month_rollup = {learner: dict(sorted(mon.items()))
                    for learner, mon in learner_months.items()}
    return {
        'rows': rows,
        'learners': sum(r['size'] for r in rows),
        'unique_learners_before_cutoff': len(by_learner),
        'future_segments_excluded': future,
        'segment_count': len(snapshot['segments']),
        'as_of': cfg['as_of'], 'timezone': 'Asia/Shanghai',
        'threshold_minutes': 30, 'month_cap_minutes': int(MONTH_CAP_MINUTES),
        'merge_evidence': evidence,
        'month_rollup': month_rollup,
        'checksum': hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'method': '时段方案：按工号在上海时间轴上做并集合并，重叠/相接时段只算一次并保留来源编号；按ISO周一与每月1日拆分，跨周跨月不重复。单周合并学时满30分钟才计回访（不满不计0人，按未达标处理），队列周=该学员首次达标周；目标周周日≤截至日才成熟，未成熟显示null。月度封顶600分钟，由结算账本另行入账，本矩阵仅展示原始合并学时。',
    }

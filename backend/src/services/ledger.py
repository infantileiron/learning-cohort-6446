"""Monthly settlement ledger.

Invariants:
- Posted LedgerMonth rows and their LedgerEntry rows are never rewritten.
- A revision changing a posted month produces a correction into the next
  still-open (pending) month; the original month keeps its basis.
- Corrections are computed on the CAPPED monthly amount (max 600 min).
- Settlement is idempotent: entries carry a natural unique key, so a retry
  after an interrupted run never double-books.
- Revisions take row locks (learner's ledger rows, learner+period order) and
  settlement takes the same locks, so concurrent revision/settlement stay
  consistent on MySQL/InnoDB.
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from src.models.entities import (StudySegment, LedgerMonth, LedgerCorrection,
                                 LedgerEntry, SettlementJob)
from src.services.periods import merge_intervals, aggregate_months, cap_minutes

D = Decimal


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def raw_month_minutes(s, learner):
    segs = [{'code': r.code, 'started_at': r.started_at, 'ended_at': r.ended_at}
            for r in s.query(StudySegment).filter_by(learner=learner).all()]
    if not segs:
        return {}
    return {p: d['minutes'] for p, d in aggregate_months(merge_intervals(segs)).items()}


def _lock_rows(s, learner):
    stmt = select(LedgerMonth).where(LedgerMonth.learner == learner)\
        .order_by(LedgerMonth.period).with_for_update()
    return {r.period: r for r in s.execute(stmt).scalars().all()}


def _shift_month(period):
    y, m = (int(x) for x in period.split('-'))
    return f'{y + (m // 12):04d}-{(m % 12) + 1:02d}'


def _open_month(s, learner, source, locked):
    later = sorted(p for p in locked if p > source and locked[p].state == 'pending')
    if later:
        return locked[later[0]]
    # no open month: advance month by month past every existing (even posted) row
    target_period = _shift_month(source)
    while target_period in locked:
        target_period = _shift_month(target_period)
    row = LedgerMonth(learner=learner, period=target_period, state='pending',
                      computed_minutes=D('0'), last_known_minutes=D('0'),
                      capped=0, note='修订差额自动开立的未结月', updated_at=now_iso())
    s.add(row)
    s.flush()
    locked[target_period] = row
    return row


def _upsert_correction(s, learner, source, target, delta):
    reason = f'时段修订差额：原月{source}已入账不改写，按封顶后应认定总量补记'
    corr = s.query(LedgerCorrection).filter_by(
        learner=learner, source_month=source, target_month=target, reason=reason).first()
    if corr:
        corr.delta_minutes = D(str(delta))
        corr.state = 'pending'
        corr.settlement_job_id = None
        corr.applied_at = None
    else:
        corr = LedgerCorrection(learner=learner, source_month=source, target_month=target,
                                delta_minutes=D(str(delta)), reason=reason, state='pending',
                                created_at=now_iso())
        s.add(corr)
    return corr


def rebuild_learner(s, learner):
    """Recompute every month of a learner from the current segments and
    route deltas of posted months into the next open month. Caller commits."""
    locked = _lock_rows(s, learner)
    raw = raw_month_minutes(s, learner)
    periods = sorted(set(raw) | set(locked))
    for period in periods:
        capped = cap_minutes(raw.get(period, 0.0))
        capped_dec = D(str(capped))
        row = locked.get(period)
        if row is None:
            row = LedgerMonth(learner=learner, period=period, state='pending',
                              computed_minutes=capped_dec, recognized_minutes=None,
                              capped=1 if capped >= 600 else 0,
                              last_known_minutes=capped_dec, updated_at=now_iso())
            s.add(row)
            locked[period] = row
            continue
        if row.state == 'pending':
            row.computed_minutes = capped_dec
            row.last_known_minutes = capped_dec
            row.capped = 1 if capped >= 600 else 0
            row.updated_at = now_iso()
        elif row.state == 'posted':
            # immutable recognized_minutes / entries; route the capped delta onward
            delta = capped_dec - D(str(row.last_known_minutes))
            if delta != 0:
                target = _open_month(s, learner, period, locked)
                _upsert_correction(s, learner, period, target.period, float(delta))
            row.last_known_minutes = capped_dec
            row.updated_at = now_iso()
    s.flush()


def _has_entry(s, learner, period, entry_type, ref_kind, ref_id):
    return s.query(LedgerEntry).filter_by(
        learner=learner, period=period, entry_type=entry_type,
        ref_kind=ref_kind, ref_id=ref_id).first() is not None


def run_settlement(s, job):
    """Settle pending months (all, or job.period only) and apply corrections
    whose target month is being settled. Single transaction; retry-safe."""
    job.state = 'running'
    s.flush()
    stmt = select(LedgerMonth).where(LedgerMonth.state == 'pending')
    if job.period:
        stmt = stmt.where(LedgerMonth.period == job.period)
    stmt = stmt.order_by(LedgerMonth.learner, LedgerMonth.period).with_for_update()
    months = s.execute(stmt).scalars().all()
    posted_rows = applied = 0
    for row in months:
        if not _has_entry(s, row.learner, row.period, 'settlement', 'ledger_month', row.id):
            s.add(LedgerEntry(learner=row.learner, period=row.period, entry_type='settlement',
                              amount_minutes=row.computed_minutes,
                              basis=f'{row.period}合并学时封顶后应认定（封顶600分钟）',
                              ref_kind='ledger_month', ref_id=row.id,
                              settlement_job_id=job.id, created_at=now_iso()))
        corrections = s.query(LedgerCorrection).filter_by(
            learner=row.learner, target_month=row.period, state='pending')\
            .order_by(LedgerCorrection.id).all()
        corr_total = D('0')
        for corr in corrections:
            if not _has_entry(s, row.learner, row.period, 'correction',
                              'ledger_correction', corr.id):
                s.add(LedgerEntry(learner=row.learner, period=row.period,
                                  entry_type='correction', amount_minutes=corr.delta_minutes,
                                  basis=corr.reason, ref_kind='ledger_correction',
                                  ref_id=corr.id, settlement_job_id=job.id,
                                  created_at=now_iso()))
            corr.state = 'applied'
            corr.settlement_job_id = job.id
            corr.applied_at = now_iso()
            corr_total += D(str(corr.delta_minutes))
            applied += 1
        row.recognized_minutes = D(str(row.computed_minutes)) + corr_total
        row.state = 'posted'
        row.updated_at = now_iso()
        posted_rows += 1
    job.state = 'done'
    job.posted_rows = posted_rows
    job.applied_corrections = applied
    job.finished_at = now_iso()
    return {'posted_rows': posted_rows, 'applied_corrections': applied}

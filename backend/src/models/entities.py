from sqlalchemy import Column,Integer,String,JSON,Text,ForeignKey,Numeric,SmallInteger,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True,nullable=False);password=Column(String(200));role=Column(String(20))
class Event(Base):
 __tablename__='events'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);learner=Column(String(60),nullable=False,index=True);occurred_at=Column(String(40),nullable=False);course=Column(String(40));note=Column(Text,default='')
class Cohort(Base):
 __tablename__='cohorts'
 id=Column(Integer,primary_key=True);name=Column(String(100));start_week=Column(String(10));end_week=Column(String(10));as_of=Column(String(10));horizon=Column(Integer);state=Column(String(20),default='queued');result=Column(JSON,nullable=True);error=Column(Text,default='');scheme=Column(String(20),default='click')
class Intervention(Base):
 __tablename__='interventions'
 id=Column(Integer,primary_key=True);cohort_id=Column(Integer,ForeignKey('cohorts.id'));cohort_week=Column(String(10));week_index=Column(Integer);note=Column(Text);members=Column(JSON);status=Column(String(20),default='draft')
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
# ---- segment scheme: numbered study periods with explicit start/end ----
class StudySegment(Base):
 __tablename__='study_segments'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);learner=Column(String(60),nullable=False,index=True);started_at=Column(String(40),nullable=False);ended_at=Column(String(40),nullable=False);course=Column(String(40));note=Column(Text,default='');revision_of=Column(Integer,nullable=True)
# ---- monthly settlement ledger ----
class LedgerMonth(Base):
 __tablename__='ledger_months'
 __table_args__=(UniqueConstraint('learner','period',name='uq_learner_period'),)
 id=Column(Integer,primary_key=True);learner=Column(String(60),nullable=False);period=Column(String(7),nullable=False);state=Column(String(20),nullable=False,default='pending');computed_minutes=Column(Numeric(10,1),nullable=False,default=0);recognized_minutes=Column(Numeric(10,1),nullable=True);capped=Column(SmallInteger,nullable=False,default=0);last_known_minutes=Column(Numeric(10,1),nullable=False,default=0);note=Column(Text,default='');updated_at=Column(String(40));
class LedgerCorrection(Base):
 __tablename__='ledger_corrections'
 __table_args__=(UniqueConstraint('learner','source_month','target_month',name='uq_correction_src'),)
 id=Column(Integer,primary_key=True);learner=Column(String(60),nullable=False);source_month=Column(String(7),nullable=False);target_month=Column(String(7),nullable=False);delta_minutes=Column(Numeric(10,1),nullable=False);reason=Column(Text);state=Column(String(20),nullable=False,default='pending');settlement_job_id=Column(Integer,nullable=True);created_at=Column(String(40));applied_at=Column(String(40))
class LedgerEntry(Base):
 __tablename__='ledger_entries'
 __table_args__=(UniqueConstraint('learner','period','entry_type','ref_kind','ref_id',name='uq_ledger_entry'),)
 id=Column(Integer,primary_key=True);learner=Column(String(60),nullable=False);period=Column(String(7),nullable=False);entry_type=Column(String(20),nullable=False);amount_minutes=Column(Numeric(10,1),nullable=False);basis=Column(Text);ref_kind=Column(String(20));ref_id=Column(Integer);settlement_job_id=Column(Integer);created_at=Column(String(40))
class SettlementJob(Base):
 __tablename__='settlement_jobs'
 id=Column(Integer,primary_key=True);period=Column(String(7));state=Column(String(20),nullable=False,default='queued');error=Column(Text,default='');posted_rows=Column(Integer,nullable=False,default=0);applied_corrections=Column(Integer,nullable=False,default=0);created_at=Column(String(40));finished_at=Column(String(40))

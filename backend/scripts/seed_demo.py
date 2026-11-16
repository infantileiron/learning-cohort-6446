import random
from datetime import date,timedelta,datetime,timezone
from zoneinfo import ZoneInfo
from src.config.database import Base,engine,Session
from src.models.entities import User,Event,StudySegment
from src.utils.security import hash_password
from src.services.ledger import rebuild_learner
def seed():
 Base.metadata.create_all(engine);rng=random.Random(3114);start=date(2026,9,21)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  for i in range(200):
   first=i//25;learner=f'CQ-{i+1:03}'
   for w in range(first,9):
    if w!=first and rng.random()>.82-.07*(w-first):continue
    day=start+timedelta(weeks=w,days=1+i%3);stamp=day.isoformat()+'T02:00:00+00:00'
    code=f'{learner}-W{w}'
    if not s.query(Event).filter_by(code=code).first():s.add(Event(code=code,learner=learner,occurred_at=stamp,course=('数据素养','服务沟通','安全规范')[i%3],note='学习平台正常上报'))
    if i%17==0:
     code+='-DUP'
     if not s.query(Event).filter_by(code=code).first():s.add(Event(code=code,learner=learner,occurred_at=day.isoformat()+'T04:00:00+00:00',course='数据素养',note='同周重复回访，不重复计人数'))
  s.commit()
  # ---- segment scheme seed: numbered start/end periods, cross-device overlaps & cross-month ----
  rng2=random.Random(4227)
  for i in range(60):
   learner=f'CQ-{i+1:03}';first=i//12
   for w in range(first,7):
    if w!=first and rng2.random()>.78:continue
    base=datetime.combine(start+timedelta(weeks=w,days=1+i%4),datetime.min.time()).replace(hour=1,tzinfo=ZoneInfo('Asia/Shanghai'))
    minutes=20+rng2.randint(0,40)
    st=base.astimezone(timezone.utc);en=(base+timedelta(minutes=minutes)).astimezone(timezone.utc)
    code=f'{learner}-S{w}'
    if not s.query(StudySegment).filter_by(code=code).first():
     s.add(StudySegment(code=code,learner=learner,started_at=st.isoformat(timespec='seconds'),ended_at=en.isoformat(timespec='seconds'),course=('数据素养','服务沟通','安全规范')[i%3],note='带编号学习时段'))
    if i%13==0: # second device overlaps the same period by 15 minutes
     ov=(base+timedelta(minutes=max(5,minutes-15))).astimezone(timezone.utc)
     ocode=code+'-X'
     if not s.query(StudySegment).filter_by(code=ocode).first():
      s.add(StudySegment(code=ocode,learner=learner,started_at=ov.isoformat(timespec='seconds'),ended_at=(ov+timedelta(minutes=25)).astimezone(timezone.utc).isoformat(timespec='seconds'),course='数据素养',note='跨设备重叠时段，合并只算一次'))
  s.commit()
  for learner in {r.learner for r in s.query(StudySegment).all()}:rebuild_learner(s,learner)
  s.commit()
  print({'users':s.query(User).count(),'events':s.query(Event).count(),'segments':s.query(StudySegment).count(),'learners':len({r.learner for r in s.query(Event).all()})})
if __name__=='__main__':seed()

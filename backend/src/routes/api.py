import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db,Session
from src.models.entities import (User,Event,Cohort,Intervention,Audit,StudySegment,
 LedgerMonth,LedgerCorrection,LedgerEntry,SettlementJob)
from src.schemas.business import (Login,EventInput,CohortInput,InterventionInput,NoteInput,
 SegmentInput,SegmentBatch,SettlementInput)
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.interventions import draft
from src.services.analysis import calculate as click_calculate
from src.services.periods import calculate as segment_calculate,merge_intervals,aggregate_weeks,aggregate_months
from src.services.ledger import rebuild_learner,run_settlement,now_iso
from src.controllers.business import ensure_cohort,ensure_intervention
router=APIRouter()
def _enqueue(queue,value):
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush(queue,value);return True
 except redis.RedisError:return False
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
# ---------------- legacy click events (retained) ----------------
@router.get('/events')
def events(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Event).order_by(Event.id.desc()).all()]
@router.post('/events')
def event(data:EventInput,u=Depends(editor),s=Depends(db)):
 existing=s.query(Event).filter_by(code=data.code).first()
 if existing:
  if all(getattr(existing,k)==v for k,v in data.model_dump().items()):return dump(existing)
  raise HTTPException(409,'同事件编号的内容冲突，请修订原记录或使用新编号')
 r=Event(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:
  s.rollback();other=s.query(Event).filter_by(code=data.code).first()
  if other and all(getattr(other,k)==v for k,v in data.model_dump().items()):return dump(other)
  raise HTTPException(409,'同事件编号的内容冲突')
 audit(s,u,'录入学习事件 '+r.code);return dump(r)
@router.put('/events/{i}')
def edit_event(i:int,data:EventInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Event,i)
 if not r:raise HTTPException(404,'事件不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'事件编号重复')
 audit(s,u,'修订学习事件 '+str(i));return dump(r)
# ---------------- numbered study segments ----------------
@router.get('/segments')
def segments(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(StudySegment).order_by(StudySegment.id.desc()).all()]
def _store_segment(s,data,revision_of=None):
 existing=s.query(StudySegment).filter_by(code=data.code).first()
 payload=data.model_dump()
 if existing:
  if all(getattr(existing,k)==v for k,v in payload.items()):return existing,False
  raise HTTPException(409,'同时段编号的内容冲突，请按记录ID显式修订')
 r=StudySegment(**payload,revision_of=revision_of);s.add(r);s.flush();return r,True
def _rebuild_and_note(s,u,learners,action):
 s.commit()
 for learner in sorted(set(learners)):rebuild_learner(s,learner)
 s.commit()
 for learner in sorted(set(learners)):audit(s,u,action+' 重建账本 '+learner)
@router.post('/segments')
def add_segment(data:SegmentInput,u=Depends(editor),s=Depends(db)):
 r,created=_store_segment(s,data)
 if not created:return dump(r)
 _rebuild_and_note(s,u,[r.learner],'录入学习时段 '+r.code);return dump(r)
@router.post('/segments/import')
def import_segments(batch:SegmentBatch,u=Depends(editor),s=Depends(db)):
 rows=[];learners=[]
 for data in batch.segments:
  r,created=_store_segment(s,data)
  rows.append({'code':r.code,'id':r.id,'created':created});learners.append(r.learner)
 _rebuild_and_note(s,u,learners,'批量导入学习时段')
 audit(s,u,f'批量导入学习时段 {len(batch.segments)} 条');return {'received':len(batch.segments),'rows':rows}
@router.put('/segments/{i}')
def edit_segment(i:int,data:SegmentInput,u=Depends(editor),s=Depends(db)):
 r=s.get(StudySegment,i)
 if not r:raise HTTPException(404,'学习时段不存在')
 before=r.learner
 if data.code!=r.code and s.query(StudySegment).filter_by(code=data.code).first():raise HTTPException(409,'时段编号已被其他记录占用')
 for k,v in data.model_dump().items():setattr(r,k,v)
 r.revision_of=(r.revision_of or i)
 try:s.flush()
 except IntegrityError:s.rollback();raise HTTPException(409,'时段编号重复')
 learners={before,r.learner}
 for learner in learners:rebuild_learner(s,learner)
 s.commit()
 for learner in sorted(learners):audit(s,u,f'修订学习时段 {i} 重建账本 {learner}')
 return dump(r)
@router.get('/segments/merge-basis')
def merge_basis(u=Depends(current),s=Depends(db)):
 by={}
 for r in s.query(StudySegment).order_by(StudySegment.id).all():
  by.setdefault(r.learner,[]).append({'code':r.code,'started_at':r.started_at,'ended_at':r.ended_at})
 out={}
 for learner,segs in by.items():
  merged=merge_intervals(segs)
  out[learner]={'merged':[{'start':m['start'].isoformat(),'end':m['end'].isoformat(),
   'minutes':m['minutes'],'sources':m['sources']} for m in merged],
   'weeks':aggregate_weeks(merged),'months':aggregate_months(merged)}
 return out
# ---------------- cohorts (two frozen schemes) ----------------
@router.get('/cohorts')
def cohorts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Cohort).order_by(Cohort.id.desc()).all()]
@router.post('/cohorts')
def cohort(data:CohortInput,u=Depends(editor),s=Depends(db)):
 cfg=data.model_dump(mode='json')
 if data.scheme=='segment':
  source=[dump(r) for r in s.query(StudySegment).order_by(StudySegment.id).all()]
  if not source:raise HTTPException(409,'没有学习时段，无法建立时段方案队列')
  snapshot={'config':cfg,'segments':source}
 else:
  snapshot={'config':cfg,'events':[dump(r) for r in s.query(Event).order_by(Event.id).all()]}
 r=Cohort(**cfg,result={'snapshot':snapshot});s.add(r);s.commit()
 if _enqueue('cohort:jobs',r.id):
  audit(s,u,'提交'+('时段' if data.scheme=='segment' else '点击')+'队列 '+str(r.id));return dump(r)
 # Redis unavailable: calculate inline so the demo stays fully functional
 try:
  calc=segment_calculate if data.scheme=='segment' else click_calculate
  r.result={**calc(snapshot),'snapshot':snapshot};r.state='done';s.commit()
 except Exception as e:
  r.state='failed';r.error=str(e);s.commit();raise HTTPException(422,r.error)
 audit(s,u,'内联计算'+('时段' if data.scheme=='segment' else '点击')+'队列 '+str(r.id));return dump(r)
@router.get('/cohorts/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_cohort(s,i))
@router.get('/cohorts/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_cohort(s,i)
 if r.state!='done':raise HTTPException(409,'计算成功后才能导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2,default=str),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="learning-cohort-{i}.json"'})
# ---------------- interventions ----------------
@router.get('/interventions')
def interventions(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Intervention).order_by(Intervention.id.desc()).all()]
@router.post('/interventions')
def intervention(data:InterventionInput,u=Depends(editor),s=Depends(db)):
 r=draft(s,ensure_cohort(s,data.cohort_id),data);audit(s,u,'生成干预清单 '+str(r.id));return dump(r)
@router.put('/interventions/{i}')
def edit_intervention(i:int,data:NoteInput,u=Depends(editor),s=Depends(db)):
 r=ensure_intervention(s,i)
 if r.status!='draft':raise HTTPException(409,'已签核清单不可修改')
 r.note=data.note;s.commit();audit(s,u,'修订干预说明 '+str(i));return dump(r)
@router.post('/interventions/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=ensure_intervention(s,i)
 if r.status!='draft':raise HTTPException(409,'已签核，不可重复签核')
 r.status='approved';s.commit();audit(s,u,'签核干预清单 '+str(i));return dump(r)
@router.get('/interventions/{i}/export')
def action_export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_intervention(s,i);return dump(r)
# ---------------- monthly settlement ledger ----------------
@router.get('/ledger/months')
def ledger_months(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(LedgerMonth).order_by(LedgerMonth.learner,LedgerMonth.period).all()]
@router.get('/ledger/entries')
def ledger_entries(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(LedgerEntry).order_by(LedgerEntry.learner,LedgerEntry.period,LedgerEntry.id).all()]
@router.get('/ledger/corrections')
def ledger_corrections(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(LedgerCorrection).order_by(LedgerCorrection.id.desc()).all()]
@router.get('/settlements')
def settlements(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(SettlementJob).order_by(SettlementJob.id.desc()).all()]
@router.post('/settlements')
def create_settlement(data:SettlementInput,u=Depends(editor),s=Depends(db)):
 job=SettlementJob(period=data.period,state='queued',created_at=now_iso());s.add(job);s.commit()
 if not _enqueue('settlement:jobs',job.id):
  run_settlement(s,job);s.commit()
 audit(s,u,('月度结算 '+str(data.period or '全部'))+' 作业 '+str(job.id));return dump(job)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]

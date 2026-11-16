import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Cohort,SettlementJob
from src.services.analysis import calculate as click_calculate
from src.services.periods import calculate as segment_calculate
from src.services.ledger import run_settlement
try:
 r=redis.Redis.from_url(os.environ['REDIS_URL'])
 r.ping()
except Exception:
 r=None
def enqueue(queue,value):
 if r is None:return False
 try:r.rpush(queue,value);return True
 except redis.RedisError:return False
def blpop(queue):
 if r is None:return None
 try:return r.blpop(queue,timeout=3)
 except redis.RedisError:return None
def recover():
 with Session() as recovery:
  for pending in recovery.query(Cohort).filter(Cohort.state.in_(['queued','running'])).all():
   pending.state='queued';enqueue('cohort:jobs',pending.id)
  for job in recovery.query(SettlementJob).filter(SettlementJob.state.in_(['queued','running'])).all():
   job.state='queued';enqueue('settlement:jobs',job.id)
  recovery.commit()
def process_cohort(item):
 with Session() as s:
  row=s.get(Cohort,int(item))
  if not row or row.state!='queued':return
  snapshot=row.result['snapshot'];row.state='running';s.commit()
  try:
   calc=segment_calculate if row.scheme=='segment' else click_calculate
   row.result={**calc(snapshot),'snapshot':snapshot};row.state='done'
   Path('/artifacts/'+str(row.id)+'.json').write_text(json.dumps(row.result,ensure_ascii=False,default=str))
  except Exception as e:row.state='failed';row.error=str(e)
  s.commit()
def process_settlement(item):
 with Session() as s:
  job=s.get(SettlementJob,int(item))
  if not job or job.state=='done':return
  if job.state=='queued':job.state='running';s.commit()
  try:run_settlement(s,job);s.commit()
  except Exception as e:
   s.rollback();job=s.get(SettlementJob,int(item));job.state='failed';job.error=str(e);s.commit()
def main():
 recover()
 while True:
  Path('/tmp/heartbeat').touch()
  try:
   item=blpop('cohort:jobs')
   if item:process_cohort(item[1]);continue
   item=blpop('settlement:jobs')
   if item:process_settlement(item[1]);continue
  except Exception:logging.exception('worker');time.sleep(2)
if __name__=='__main__':main()

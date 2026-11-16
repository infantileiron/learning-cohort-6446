from datetime import datetime,date,timezone
from pydantic import BaseModel,Field,field_validator,model_validator
from typing import Literal,List
from src.constants.enums import SCHEMES
def _ts(v):
 d=datetime.fromisoformat(v.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('时间必须带时区，例如+08:00')
 return d.astimezone(timezone.utc).isoformat(timespec='seconds')
class Login(BaseModel):email:str;password:str
class EventInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 learner:str=Field(min_length=1,max_length=60)
 occurred_at:str
 course:Literal['数据素养','服务沟通','安全规范']
 note:str=Field(default='',max_length=1000)
 @field_validator('occurred_at')
 @classmethod
 def timestamp(cls,v):return _ts(v)
class SegmentInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 learner:str=Field(min_length=1,max_length=60)
 started_at:str
 ended_at:str
 course:Literal['数据素养','服务沟通','安全规范']
 note:str=Field(default='',max_length=1000)
 @field_validator('started_at','ended_at')
 @classmethod
 def timestamp(cls,v):return _ts(v)
 @model_validator(mode='after')
 def order(self):
  if self.ended_at<=self.started_at:raise ValueError('结束时间必须晚于开始时间')
  return self
class SegmentBatch(BaseModel):
 segments:List[SegmentInput]=Field(min_length=1,max_length=2000)
class CohortInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 start_week:date;end_week:date;as_of:date
 horizon:int=Field(default=5,ge=1,le=8)
 scheme:Literal['click','segment']='click'
 @model_validator(mode='after')
 def windows(self):
  if self.scheme not in SCHEMES:raise ValueError('未知计算方案')
  if self.start_week.weekday()!=0 or self.end_week.weekday()!=0:raise ValueError('队列起止周必须是ISO周一')
  if self.start_week>self.end_week or self.end_week>self.as_of:raise ValueError('起周≤止周≤截至日')
  if (self.end_week-self.start_week).days>365:raise ValueError('小型项目队列窗口最多一年')
  return self
class InterventionInput(BaseModel):
 cohort_id:int=Field(gt=0)
 cohort_week:str=Field(min_length=10,max_length=10)
 week_index:int=Field(ge=1,le=8)
 note:str=Field(min_length=8,max_length=2000)
class NoteInput(BaseModel):note:str=Field(min_length=8,max_length=2000)
class SettlementInput(BaseModel):
 period:str|None=Field(default=None,pattern=r'^\d{4}-\d{2}$')

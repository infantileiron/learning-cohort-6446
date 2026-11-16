/** @typedef {{id:number,code:string,learner:string,occurred_at:string,course:string,note:string}} Event */
/** @typedef {{id:number,code:string,learner:string,started_at:string,ended_at:string,course:string,note:string,revision_of:?number}} StudySegment */
/** @typedef {{id:number,name:string,start_week:string,end_week:string,as_of:string,horizon:number,state:string,scheme:'click'|'segment',result:object}} Cohort */
/** @typedef {{id:number,cohort_id:number,cohort_week:string,week_index:number,members:string[],note:string,status:string}} Intervention */
/** @typedef {{id:number,learner:string,period:string,state:'pending'|'posting'|'posted',computed_minutes:number,recognized_minutes:?number,capped:number,last_known_minutes:number,note:string}} LedgerMonth */
/** @typedef {{id:number,learner:string,period:string,entry_type:'settlement'|'correction',amount_minutes:number,basis:string,ref_kind:string,ref_id:number,settlement_job_id:?number}} LedgerEntry */
/** @typedef {{id:number,learner:string,source_month:string,target_month:string,delta_minutes:number,reason:string,state:'pending'|'applied'}} LedgerCorrection */
/** @typedef {{id:number,period:?string,state:string,error:string,posted_rows:number,applied_corrections:number}} SettlementJob */

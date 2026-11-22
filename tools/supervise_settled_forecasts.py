"""Bounded resume of existing research lanes; respects review pauses and operator sleep."""
from tools.resume_settled_forecasts import resume as resume_collector
from tools.evaluate_settled_forecasts import resume as resume_evaluator


def ensure(storage,state,*,can_start,now):
    result={}
    for name,resume in [('collector',resume_collector),('evaluator',resume_evaluator)]:
        if not can_start:
            result[name]={'state':'paused_backend_or_operator_sleep'}
            continue
        attempts=state.setdefault('settled_starts',{}).setdefault(name,[])
        attempts[:]=[at for at in attempts if 0<=now.timestamp()-at<3600]
        if len(attempts)>=3:
            result[name]={'state':'restart_budget_exhausted_review_required'}
            continue
        try:
            observed=resume(storage)
            if observed.get('state') in {'settled_collector_started','evaluator_started'}:
                attempts.append(now.timestamp())
            result[name]=observed
        except Exception as exc:
            result[name]={'state':'blocked_review_required','error':type(exc).__name__}
    return result

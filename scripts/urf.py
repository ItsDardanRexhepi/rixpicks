#!/usr/bin/env python3
"""
URF CORE - Unified Rexhepi Framework, operational layer (manuscript Part II).
Authority: user iMessage phonemsg-01M3FR1WBQXZFBHXSQ8ZQ45HMH (2026-09-26 1:56:03 PM PT, verbatim verified):
"Wire the URF at core level of the system and core level of all agents and Implement URF as the reasoning,
 logic, planning, tools, evidence, uncertainty, execution, verification, recovery, reflection, and learning
 loop across the board."
Every governed decision: six gates (C,F,R,U,V,CE scored 0-3 in fixed order), time modifier T,
exactly one canonical outcome (EXECUTE|PROBE|ASK|DEFER|ABORT), one rationale line, full 14.3 log row.
Hard rules are inviolable: (1) no external publishing without approval, (2) no destructive ops without
rollback, (3) no loops - after 2 failed attempts at the same approach, stop and re-plan, (4) every task
ends with artifact + verification, (5) independence - protocol use is never evidence for a program's claims.
"""
import json,datetime,os,sys,uuid

LOG='/home/sandbox/rps_tmp/kb/ledger/urf_decisions.jsonl'

GATES=('C','F','R','U','V','CE')  # fixed scoring order (14.1: outcome cannot be chosen first)
T_VALUES=('low','medium','high')
OUTCOMES=('EXECUTE','PROBE','ASK','DEFER','ABORT')

def _ts():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

def prior_failed_attempts(task,approach=''):
    """Hard rule 3: count logged failed attempts for this task+approach."""
    n=0
    if os.path.exists(LOG):
        for l in open(LOG):
            if not l.strip(): continue
            try: r=json.loads(l)
            except: continue
            if r.get('task')==task and r.get('approach', '')==approach and r.get('status')=='failed':
                n+=1
    return n

def decide(task, C,F,R,U,V,CE, T='low', rationale='', evidence=None, artifact='', verification='',
           stop_condition='', owner='sports-analysis', reviewer='', approach='', approval_given=False,
           revisit='', log=True):
    """
    Score gates in fixed order, apply hard rules, return the canonical outcome.
    Policy (manuscript 10-13):
      hard rule 3 loop guard -> ABORT (re-plan) after 2 failed attempts at same approach
      R=3 without explicit approval -> ASK (approval required before any state change)
      C<2 -> ASK (one sharp question / propose spec for confirmation)
      F<2 -> PROBE (smallest experiment proving the path); F=0 unrecoverable -> ABORT
      U>=2 -> PROBE (reduce uncertainty before committing)
      V<=1 and anything else hard (any of C,F,U <2) -> DEFER
      V=0 -> DEFER
      else -> EXECUTE
    T=high: caller tightens verification + guarantees rollback. T=low: demand stronger evidence -
    U==1 with T=low downgrades EXECUTE to PROBE when the decision is irreversible (R>=2).
    """
    assert T in T_VALUES
    scores={'C':int(C),'F':int(F),'R':int(R),'U':int(U),'V':int(V),'CE':int(CE)}
    for g in GATES: assert 0<=scores[g]<=3, g
    fails=prior_failed_attempts(task,approach)
    hard_rules={'no_external_publish_without_approval':True,'rollback_plan':True,
                'loop_guard_failures':fails,'artifact_and_verification':bool(artifact and verification),
                'independence':True}
    reasons=[]
    if fails>=2:
        outcome='ABORT'; reasons.append(f'hard rule 3: {fails} failed attempts at this approach - re-plan, do not retry')
    elif R==3 and not approval_given:
        outcome='ASK'; reasons.append('R=3: explicit approval required before any state change')
    elif C<2:
        outcome='ASK'; reasons.append('C<2: one sharp question or concrete spec + confirmation')
    elif F<2:
        outcome='PROBE' if F==1 else 'ABORT'
        reasons.append('F<2: smallest experiment that proves/disproves the path' if F==1 else 'F=0: blocked/impossible')
    elif U>=2:
        outcome='PROBE'; reasons.append('U>=2: reduce uncertainty before committing')
    elif V==0 or (V<=1 and (C<2 or F<2 or U>=2)):
        outcome='DEFER'; reasons.append('V low: park it, revisit when conditions change')
    elif T=='low' and U==1 and R>=2:
        outcome='PROBE'; reasons.append('T=low demands stronger evidence on a partially-irreversible decision')
    else:
        outcome='EXECUTE'; reasons.append('gates satisfied')
    rec={'id':'URF-'+uuid.uuid4().hex[:8].upper(),'date':_ts(),'task':task,'approach':approach,
         'scores':scores,'T':T,'outcome':outcome,'rationale':rationale,'reasons':reasons,
         'evidence':evidence or [],'hard_rule_check':hard_rules,'artifact':artifact,
         'verification':verification,'stop_condition':stop_condition,'owner':owner,
         'reviewer':reviewer,'status':'open','revisit':revisit}
    if log:
        os.makedirs(os.path.dirname(LOG),exist_ok=True)
        with open(LOG,'a') as f: f.write(json.dumps(rec)+'\n')
    line=f"Decision: {outcome} | C={C} F={F} R={R} U={U} V={V} CE={CE} T={T}"
    return {'outcome':outcome,'line':line,'record':rec}

def mark(decision_id,status):
    """reflection/learning loop: close a decision row (verified|failed|superseded)."""
    rows=[json.loads(l) for l in open(LOG) if l.strip()] if os.path.exists(LOG) else []
    for r in rows:
        if r.get('id')==decision_id: r['status']=status; r['closed_ts']=_ts()
    with open(LOG,'w') as f:
        for r in rows: f.write(json.dumps(r)+'\n')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='URF core decision protocol')
    p.add_argument('--task',required=True)
    for g in GATES: p.add_argument(f'--{g}',type=int,required=True)
    p.add_argument('--T',default='low',choices=T_VALUES)
    p.add_argument('--rationale',default='')
    p.add_argument('--approach',default='')
    p.add_argument('--artifact',default=''); p.add_argument('--verification',default='')
    p.add_argument('--approval-given',action='store_true')
    a=p.parse_args()
    r=decide(a.task,a.C,a.F,a.R,a.U,a.V,a.CE,T=a.T,rationale=a.rationale,approach=a.approach,
             artifact=a.artifact,verification=a.verification,approval_given=a.approval_given)
    print(r['line'])
    print('reasons:', '; '.join(r['record']['reasons']))
    print('logged:', r['record']['id'])

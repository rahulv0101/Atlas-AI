import pandas as pd
from tools.validate_current_smc import ContextCache,MODELS
from atlas_ai.testing.smc_validation import HistoricalFeed
from atlas_ai.data.top_down import TIMEFRAMES,MINUTES,collect


def test_exact_clock_cache_matches_direct_context_and_never_reuses_stale_ages(tmp_path):
    frames={}
    for tf in TIMEFRAMES:
        end=pd.Timestamp('2026-11-19T12:00Z').floor('D') if tf=='D1' else pd.Timestamp('2026-11-19T12:00Z')
        times=pd.date_range(end=end,periods=50,freq=pd.Timedelta(minutes=MINUTES[tf]))
        prices=[2000.+i for i in range(50)]
        frames[tf]=pd.DataFrame({'time':times,'open':prices,'close':prices,'high':[x+1 for x in prices],'low':[x-1 for x in prices]})
    feed=HistoricalFeed(frames);direct=HistoricalFeed(frames);cache=ContextCache(tmp_path/'cache.sqlite',feed,'UTC')
    previous=None
    try:
        for now in [pd.Timestamp('2026-11-19T12:03Z'),pd.Timestamp('2026-11-19T12:08Z')]:
            direct.now=now;value=cache(now)
            assert value==collect(direct,now,broker_timezone='UTC')
            assert cache(now)==value
            if previous is not None:assert value['evidence']['M15']['freshness_age_seconds']==previous+300
            previous=value['evidence']['M15']['freshness_age_seconds']
        assert cache.writes==2
    finally:cache.close()


def test_declared_cohort_has_framework_and_unique_model_lanes():
    assert len(MODELS)==len(set(MODELS))==6
    assert 'smc_framework_v4' in MODELS


def test_shared_smc_status_exposes_historical_progress_without_broker_authority(tmp_path):
    from datetime import datetime,timezone
    from atlas_ai.atomic_files import atomic_json
    from tools.learn_candidate_ranker import save_signed
    from atlas_ai.research_status import load_research_progress,research_answer
    forward=tmp_path/'forward';forward.mkdir();review=tmp_path/'review';review.mkdir()
    now=datetime.now(timezone.utc).isoformat()
    save_signed(forward,'manifest',{'broker_eligible':False})
    atomic_json(forward/'paper_status.json',{'state':'collecting_paper','checked_at':now})
    atomic_json(tmp_path/'smc_validation_active.json',{'run_dir':str(forward)})
    save_signed(review,'protocol',{'broker_eligible':False,'auto_promotion':False})
    atomic_json(review/'progress.json',{'phase':'historical_review','model':'smc_framework_v4','bar':20,'total':100,'checked_at':now})
    atomic_json(tmp_path/'smc_review_active.json',{'run_dir':str(review)})
    progress=load_research_progress(tmp_path)
    value=progress['smc_validation']['historical_review']
    assert value['bar']==20 and not value['stale'] and not value['broker_eligible']
    assert 'bar 20 of 100' in research_answer(progress,'smc validation')
    assert len(research_answer(progress,'smc validation',voice=True))<len(research_answer(progress,'smc validation'))


def test_unexpected_historical_review_authority_is_not_reported_as_valid(tmp_path):
    from atlas_ai.atomic_files import atomic_json
    from tools.learn_candidate_ranker import save_signed
    from atlas_ai.research_status import load_research_progress
    directory=tmp_path/'review';directory.mkdir()
    save_signed(directory,'protocol',{'broker_eligible':True,'auto_promotion':False})
    atomic_json(tmp_path/'smc_review_active.json',{'run_dir':str(directory)})
    assert load_research_progress(tmp_path)['smc_validation']['historical_review']['stale']

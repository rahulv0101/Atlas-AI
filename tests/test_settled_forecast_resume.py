from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
from atlas_ai.atomic_files import atomic_json
from atlas_ai.learning.observation_checkpoint import observation_lock
from tools.learn_candidate_ranker import save_signed
from tools.resume_settled_forecasts import resume


def fixture(tmp_path,state='collecting_settled_candidate_forecasts'):
    storage=tmp_path/'storage';directory=storage/'collector';directory.mkdir(parents=True)
    save_signed(directory,'protocol',{'broker_eligible':False,'auto_promotion':False,'orders_sent':0,
        'deadline':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
    atomic_json(directory/'status.json',{'state':state})
    atomic_json(storage/'settled_m5_forward_active.json',{'run_dir':str(directory)})
    return storage,directory


def test_existing_worker_is_never_duplicated(tmp_path):
    storage,directory=fixture(tmp_path);start=Mock()
    with observation_lock(directory/'collector.lock'):
        assert resume(storage,start=start)['state']=='existing_settled_collector_running'
    start.assert_not_called()


def test_revision_pause_cannot_be_automatically_cleared(tmp_path):
    storage,_=fixture(tmp_path,'blocked_review_required');start=Mock()
    assert resume(storage,start=start)['state']=='blocked_review_required'
    start.assert_not_called()


def test_resume_uses_project_python_and_hidden_child(tmp_path):
    storage,directory=fixture(tmp_path)
    python=tmp_path/'.venv/Scripts/pythonw.exe';python.parent.mkdir(parents=True);python.write_text('test stub')
    start=Mock(return_value=SimpleNamespace(pid=123))
    assert resume(storage,start=start)['pid']==123
    command=start.call_args.args[0]
    assert command[0]==str(python) and '--initialize' not in command and '--watch' in command

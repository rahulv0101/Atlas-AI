from tools.install_atlas_startup import logon_task_script


def test_logon_recovery_never_requests_elevation_password_or_unbounded_retries(tmp_path):
    script=logon_task_script(tmp_path/"Atlas AI")
    assert '-LogonType Interactive -RunLevel Limited' in script
    assert '-MultipleInstances IgnoreNew' in script and '-RestartCount 2' in script
    assert "PT30S" in script and '--at-logon' in script
    assert '-Password' not in script and 'Highest' not in script


def test_project_paths_are_literal_even_with_apostrophes(tmp_path):
    script=logon_task_script(tmp_path/"Operator's Atlas")
    assert "Operator''s Atlas" in script
    assert 'atlas_fullstack_startup.pyw' in script

"""An update must not launch an interpreter missing its required packages."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'snapgen_modules'))
import snapgen_updater as U


def test_runtime_probe_ignores_inherited_pythonpath(tmp_path, monkeypatch):
    calls=[]
    def run(args, **kwargs):
        calls.append((args,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(U.subprocess,'run',run)
    assert U._runtime_ready(tmp_path)
    assert '-I' in calls[0][0] and 'PIL' in calls[0][0][-1] and 'qcloud_cos' in calls[0][0][-1]


@pytest.mark.parametrize('setup_exit,ready,starts', [(0,True,True),(1,True,True),(1,False,False),(0,False,False)])
def test_update_starts_only_when_runtime_imports_succeed(tmp_path,monkeypatch,setup_exit,ready,starts):
    (tmp_path/'setup_and_run.bat').write_text('test setup')
    calls=[]
    monkeypatch.setattr(U.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=setup_exit))
    monkeypatch.setattr(U,'_runtime_ready',lambda root:ready)
    monkeypatch.setattr(U.subprocess,'Popen',lambda *args,**kwargs:calls.append((args,kwargs)))
    if starts:
        U._start_after_update(tmp_path)
        assert len(calls)==1 and str(tmp_path/'snapgen_gui_v2.py') in calls[0][0][0]
    else:
        with pytest.raises(U.UpdateError,match='แพ็กเกจ Python ยังไม่ครบ'):
            U._start_after_update(tmp_path)
        assert not calls


def test_setup_skips_pip_only_after_isolated_import_check():
    source=(Path(__file__).resolve().parents[1]/'setup_and_run.bat').read_bytes()
    assert source.count(b'\r\n')==source.count(b'\n')
    assert b'"%VENV_PY%" -I -B -c "import sys, tkinter, PIL, websocket, qcloud_cos;' in source
    assert source.index(b'goto :packages_ready') < source.index(b'pip install Pillow') < source.index(b'\r\n:packages_ready\r\n')

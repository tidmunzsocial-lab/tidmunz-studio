"""Exercise the production storyboard stage with isolated, controlled image providers."""
import threading
import time
from pathlib import Path

import pytest
from test_video_auto_scene_provider import N, load


@pytest.mark.parametrize('provider', ['gpt_web', 'snapgen'])
def test_two_sheets_run_together_and_pair_results_keep_their_shots(tmp_path, provider):
    groups=[[0,1],[2,3],[4,5],[6,7]]
    scenes=[{'prompt':f'shot {i}'} for i in range(8)]
    state={'project':{'scenes':scenes,'aspect':'16:9'},'folder':str(tmp_path),'lock':threading.RLock()}
    barrier=threading.Barrier(2); lock=threading.Lock(); active=0; peak=0; requests=[]; anchors=[]; saved=[]
    def previous(_folder,first):
        anchors.append(first)
        return None if first==1 else 'prior-completed-sheet.png'
    def make_image(prompt,refs,folder,name,aspect,**options):
        nonlocal active,peak
        first=int(name[6:9]);
        with lock:
            active+=1; peak=max(peak,active); requests.append((first,list(refs),dict(options)))
        barrier.wait(timeout=4)
        if first in (1,5):time.sleep(.05)
        path=folder/(name+'.png');path.write_text(name)
        with lock:active-=1
        return str(path)
    def crop(sheet,_count,panels):
        for p in panels:p.write_text(Path(sheet).name)
    noop=lambda *a,**k:None
    scope=dict(vars(N),state=state,video_mode=True,board_groups=lambda *a,**k:groups,
        check_script_matches_audio=noop,ensure_story_in_history=noop,ensure_continuity=noop,ensure_bodies=noop,
        ensure_board_template=lambda *a:'grid.png',character_refs=lambda:{},
        image_provider_for=lambda stage:provider,previous_board_sheet=previous,
        attachments_for=lambda scene:[scene['prompt']+'.png'],board_request=lambda *a,**k:'board prompt',
        style_text=lambda:'style',make_image=make_image,crop_board=crop,check_stop=noop,
        save_project=lambda:saved.append([s.get('board') for s in scenes]),set_progress=noop,log=noop)
    load(scope,'stage_storyboard')()
    assert peak==2 and anchors==[1,5] and len(saved)==4
    assert all(Path(scene['board']).read_text()==f'sheet_{(i//2)*2+1:03d}-{(i//2)*2+2:03d}.png'
               for i,scene in enumerate(scenes))
    by_first = {first: refs for first, refs, _ in requests}
    assert set(by_first[1][1:])=={'shot 0.png','shot 1.png'}
    assert set(by_first[3][1:])=={'shot 2.png','shot 3.png'}
    assert all('prior-completed-sheet.png' in refs for first,refs,_ in requests if first>=5)
    if provider=='gpt_web':
        assert all(options.get('parallel_images') and options.get('fresh_chat') for _,_,options in requests)


def test_stop_drains_both_submitted_sheets_and_saves_successes(tmp_path):
    groups=[[0],[1],[2]];scenes=[{'prompt':str(i)} for i in range(3)]
    state={'project':{'scenes':scenes,'aspect':'16:9'},'folder':str(tmp_path),'lock':threading.RLock()}
    barrier=threading.Barrier(2);stopped=threading.Event();started=[]
    def check():
        if stopped.is_set():raise N.Stopped()
    def make_image(prompt,refs,folder,name,aspect,**kwargs):
        started.append(name);barrier.wait(timeout=4);stopped.set()
        path=folder/(name+'.png');path.write_text(name);return str(path)
    def crop(sheet,_count,panels):
        for p in panels:p.write_text(Path(sheet).name)
    noop=lambda *a,**k:None
    scope=dict(vars(N),state=state,video_mode=True,board_groups=lambda *a,**k:groups,
        check_script_matches_audio=noop,ensure_story_in_history=noop,ensure_continuity=noop,ensure_bodies=noop,
        ensure_board_template=lambda *a:'grid.png',character_refs=lambda:{},image_provider_for=lambda stage:'gpt_web',
        previous_board_sheet=lambda *a:None,attachments_for=lambda scene:[],board_request=lambda *a,**k:'board prompt',
        style_text=lambda:'style',make_image=make_image,crop_board=crop,check_stop=check,save_project=noop,
        set_progress=noop,log=noop)
    with pytest.raises(N.Stopped):load(scope,'stage_storyboard')()
    assert len(started)==2 and all(scenes[i].get('board') for i in (0,1)) and not scenes[2].get('board')

"""Exercise real two-image dispatch and scene persistence with controlled providers."""
import base64
import json
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_video_auto_scene_provider import N, load
from test_chrome_dispatch import SOURCE, run_node


def test_extension_two_lanes_out_of_order_and_text_barrier():
    code = SOURCE[SOURCE.index("let account ="):SOURCE.index("// ── the ChatGPT tab")]
    data = run_node(code + r'''
let running=false, active=0, peak=0, taken=0;
const events=[], lanes=[];
const sleep=async()=>{},badge=()=>{},isWorkerTab=()=>false;
global.fetch=()=>new Promise(()=>{});
global.chrome={storage:{local:{get:async()=>({})}},tabs:{query:async()=>[]},runtime:{
getManifest:()=>({version:'test'}),reload:()=>events.push('reload')}};
const jobs=[{id:'1',type:'image'},{id:'2',type:'image'},{id:'3',type:'image'},
{id:'text',type:'chat'},{id:'4',type:'image'},{reload:true}];
const relay=async(path,body)=>{
 if(path.startsWith('/next'))return jobs[taken++];
 events.push('result:'+body.id+':'+body.text);return {};
};
async function runJob(job,lane){
 if(job.type==='chat' && active)throw Error('text overlapped images');
 active++;peak=Math.max(peak,active);events.push('start:'+job.id);lanes.push([job.id,lane]);
 await new Promise(r=>setTimeout(r,job.id==='1'?40:5));
 active--;return {text:job.id};
}
loop().then(()=>console.log(JSON.stringify({peak,events,lanes,active})));
''')
    assert data['peak'] == 2 and data['active'] == 0
    events = data['events']
    assert events.index('result:2:2') < events.index('result:1:1')
    assert events.index('result:3:3') < events.index('start:text')
    assert events.index('result:text:text') < events.index('start:4')
    assert events[-1] == 'reload'
    assert data['lanes'][0][1] != data['lanes'][1][1]


@pytest.mark.parametrize('stop', [False, True])
def test_auto_two_jobs_preserve_out_of_order_results_and_drain(tmp_path, stop):
    scenes = [dict(prompt=f'shot {i}', characters=[f'person{i}']) for i in range(4)]
    lock = threading.RLock()
    entered = threading.Barrier(2)
    stopped = threading.Event()
    started = []
    def check_stop():
        if stopped.is_set():
            raise RuntimeError('stopped')
    def make_image(prompt, paths, folder, name, aspect, **kwargs):
        i = int(name[-3:]) - 1
        started.append(i)
        assert paths == [f'ref{i}'] and kwargs['fresh_chat'] and kwargs['parallel_images']
        if i < 2:
            entered.wait(timeout=3)
        if stop:
            stopped.set()
        if i == 0:
            time.sleep(.05)
        p = folder / (name+'.png')
        p.write_text(prompt)
        return str(p)
    project = dict(scenes=scenes, aspect='16:9')
    disk = tmp_path/'project.json'
    scope = dict(vars(N), state=dict(project=project, lock=lock),
                 attachments_for=lambda s, limit: ['ref'+s['prompt'].split()[-1]],
                 scene_prompt=lambda s:s['prompt'], make_image=make_image,
                 check_stop=check_stop, save_project=lambda:disk.write_text(json.dumps(project)),
                 log=lambda *a:None, set_progress=lambda *a:None,
                 ui=lambda *a:None, refresh_table=None, follow_shot=None)
    run = load(scope, 'run_gpt_scenes')
    if stop:
        with pytest.raises(RuntimeError, match='stopped'):
            run(range(4), scenes, tmp_path)
        assert sorted(started) == [0, 1]
    else:
        run(range(4), scenes, tmp_path)
    restored = json.loads(disk.read_text())
    for i in started:
        assert Path(restored['scenes'][i]['image']).read_text() == f'shot {i}'


def test_gpt_timeout_retries_only_failed_shot_then_continues_unstarted_jobs(tmp_path):
    scenes = [dict(prompt=f'shot {i}', characters=[f'person{i}']) for i in range(5)]
    state_lock = threading.RLock()
    first_pair = threading.Barrier(2)
    provider_attempts = {}
    active = 0
    peak = 0
    counts_lock = threading.Lock()
    project = dict(scenes=scenes, aspect='16:9')
    disk = tmp_path/'project.json'

    def make_image(prompt, _paths, folder, name, _aspect, **_kwargs):
        nonlocal active, peak
        i = int(name[-3:]) - 1
        with counts_lock:
            provider_attempts[i] = provider_attempts.get(i, 0) + 1
            attempt = provider_attempts[i]
            active += 1
            peak = max(peak, active)
        try:
            if i < 2 and attempt == 1:
                first_pair.wait(timeout=3)
            if i == 0 and attempt == 1:
                try:
                    raise TimeoutError('Unexpected: timed out')
                except TimeoutError as exc:
                    raise N.ImageProviderError('GPT request failed') from exc
            path = folder/(name+'.png')
            path.write_text(prompt)
            return str(path)
        finally:
            with counts_lock:
                active -= 1

    scope = dict(vars(N), state=dict(project=project, lock=state_lock),
                 attachments_for=lambda s, limit: ['ref'+s['prompt'].split()[-1]],
                 scene_prompt=lambda s:s['prompt'], make_image=make_image,
                 check_stop=lambda:None,
                 save_project=lambda:disk.write_text(json.dumps(project)),
                 log=lambda *a:None, set_progress=lambda *a:None,
                 ui=lambda *a:None, refresh_table=None, follow_shot=None)

    load(scope, 'run_gpt_scenes')(range(5), scenes, tmp_path)

    assert peak == 2 and active == 0
    assert provider_attempts == {0: 2, 1: 1, 2: 1, 3: 1, 4: 1}
    restored = json.loads(disk.read_text())
    for i, scene in enumerate(restored['scenes']):
        assert Path(scene['image']).read_text() == f'shot {i}'


def test_gpt_repeated_timeout_is_bounded_and_keeps_other_saved_images(tmp_path):
    scenes = [dict(prompt=f'shot {i}', characters=[f'person{i}']) for i in range(4)]
    state_lock = threading.RLock()
    provider_attempts = {}
    project = dict(scenes=scenes, aspect='16:9')
    disk = tmp_path/'project.json'

    def make_image(prompt, _paths, folder, name, _aspect, **_kwargs):
        i = int(name[-3:]) - 1
        provider_attempts[i] = provider_attempts.get(i, 0) + 1
        if i == 0:
            raise TimeoutError('Unexpected: timed out')
        path = folder/(name+'.png')
        path.write_text(prompt)
        return str(path)

    scope = dict(vars(N), state=dict(project=project, lock=state_lock),
                 attachments_for=lambda s, limit: ['ref'+s['prompt'].split()[-1]],
                 scene_prompt=lambda s:s['prompt'], make_image=make_image,
                 check_stop=lambda:None,
                 save_project=lambda:disk.write_text(json.dumps(project)),
                 log=lambda *a:None, set_progress=lambda *a:None,
                 ui=lambda *a:None, refresh_table=None, follow_shot=None)

    with pytest.raises(N.ImageProviderError, match='หมดเวลา'):
        load(scope, 'run_gpt_scenes')(range(4), scenes, tmp_path)

    assert provider_attempts == {0: 3, 1: 1, 2: 1, 3: 1}
    restored = json.loads(disk.read_text())
    assert restored['scenes'][0].get('image') is None
    for i in (1, 2, 3):
        assert Path(restored['scenes'][i]['image']).read_text() == f'shot {i}'


def test_parallel_http_results_and_refs_are_not_crossed(tmp_path, monkeypatch):
    import snapgen_image_gen as G
    monkeypatch.setitem(sys.modules, 'ai_slow2x', SimpleNamespace(enhance_image_async=lambda *a,**k:None))
    barrier = threading.Barrier(2)
    active = [0, 0]
    lock = threading.Lock()
    def urlopen(req, timeout):
        body = json.loads(req.data)
        with lock:
            active[0] += 1
            active[1] = max(active)
        barrier.wait(timeout=3)
        marker = 'ONE' if 'ONE' in body['prompt'] else 'TWO'
        # Each request carries only its own reference.
        assert body['images'] == [base64.b64encode(marker.encode()).decode()]
        with lock:
            active[0] -= 1
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return json.dumps({'data':[{'b64_json':base64.b64encode(marker.encode()).decode()}]}).encode()
        return Response()
    monkeypatch.setattr(G.urllib.request,'urlopen',urlopen)
    monkeypatch.setattr(G,'_artifact_snapshot',lambda:pytest.fail('unsafe account-wide recovery'))
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(G.generate_image, word, output_dir=tmp_path, name_hint=word,
                               parallel_images=True, conversation_state={}, save_sidecar=False,
                               is_edit=True, ref_images=[base64.b64encode(word.encode()).decode()])
                   for word in ('ONE','TWO')]
        assert [Path(f.result()).read_text() for f in futures] == ['ONE','TWO']
    assert active[1] == 2


def test_parallel_error_never_recovers_another_jobs_artifact_or_retries(tmp_path,monkeypatch):
    import snapgen_image_gen as G
    calls=[]
    def fail(*a,**k):
        calls.append(1)
        raise RuntimeError('unknown send result')
    monkeypatch.setattr(G.urllib.request,'urlopen',fail)
    monkeypatch.setattr(G,'_recover_new_artifact',lambda *a:pytest.fail('cross-job recovery'))
    monkeypatch.setattr(G,'RETRY_COUNT',5)
    with pytest.raises(RuntimeError,match='unknown send result'):
        G.generate_image('ONE',output_dir=tmp_path,parallel_images=True,conversation_state={})
    assert len(calls)==1


def test_parallel_rejects_shared_history():
    import snapgen_image_gen as G
    with pytest.raises(ValueError,match='isolated'):
        G.generate_image('ONE',parallel_images=True,use_story_history=True)


def test_overflow_keeps_named_characters_and_specific_main_location():
    scene={'characters':['ท้าวธันตะรด','ลูกชายทั้งสี่คน'], 'location':'พระราชวังเมืองบาดาล'}
    paths=['ท้าวธันตะรด.png','ลูกชายทั้งสี่คน.png','พระราชวังเมืองบาดาล.png',
           'เมืองบาดาล.png','ท้องพระโรง.png','สกุลเนตร.png']
    assert N.primary_scene_references(scene,paths,5)==paths[:3]
    assert N.primary_scene_references(scene,paths,6)==paths


def test_overflow_never_drops_an_explicit_main_character():
    scene={'characters':[f'person{i}' for i in range(6)],'location':'palace'}
    paths=[f'person{i}.png' for i in range(6)]+['palace.png']
    with pytest.raises(N.ImageProviderError,match='เรฟตัวละคร'):
        N.primary_scene_references(scene,paths,5)


def test_gpt_scene_worker_submits_only_primary_refs_when_over_limit(tmp_path):
    board=tmp_path/'panel.png';board.write_bytes(b'board')
    scene={'characters':['ท้าวธันตะรด','ลูกชายทั้งสี่คน'], 'location':'พระราชวังเมืองบาดาล',
           'board':str(board),'prompt':'new scene'}
    paths=['ท้าวธันตะรด.png','ลูกชายทั้งสี่คน.png','พระราชวังเมืองบาดาล.png',
           'เมืองบาดาล.png','ท้องพระโรง.png','สกุลเนตร.png']
    sent=[];noop=lambda *a,**k:None
    def make_image(prompt, refs, folder, name, aspect, **kwargs):
        sent.append((list(refs),kwargs));result=folder/(name+'.png');result.write_bytes(b'scene');return str(result)
    project={'scenes':[scene],'aspect':'16:9'}
    scope=dict(vars(N),state={'project':project,'lock':threading.RLock()},
        attachments_for=lambda _scene,limit=None:paths,scene_prompt=lambda s:s['prompt'],make_image=make_image,
        check_stop=noop,save_project=noop,log=noop,set_progress=noop,ui=noop,refresh_table=noop,follow_shot=noop)
    load(scope,'run_gpt_scenes')([0],[scene],tmp_path)
    assert sent[0][0]==paths[:3] and sent[0][1]['board']==str(board)
    assert Path(scene['image']).is_file()


def test_worker_tabs_allocate_distinct_ids_and_protect_both_lanes():
    code = SOURCE[SOURCE.index('function isWorkerTab('):SOURCE.index('async function waitLoaded(')]
    data = run_node(code + r'''
let next=20;
const saved={},removed=[],tabs=new Map();
global.chrome={storage:{local:{get:async keys=>Object.fromEntries(keys.filter(k=>k in saved).map(k=>[k,saved[k]])),
set:async values=>Object.assign(saved,values)}},windows:{getAll:async()=>[{id:1}]},tabs:{
get:async id=>tabs.get(id),query:async()=>[...tabs.values()],
create:async props=>{const tab={id:next++,...props,autoDiscardable:false};tabs.set(tab.id,tab);return tab;},
update:async(id,props)=>Object.assign(tabs.get(id),props),remove:async id=>{removed.push(id);tabs.delete(id);}}};
Promise.all([workerTab('workerTabId'),workerTab('workerTabId2')]).then(async ids=>{
await pruneWorkerTabs(ids[0]);console.log(JSON.stringify({ids,saved,removed}));});
''')
    assert len(set(data['ids'])) == 2
    assert data['removed'] == []
    assert set(data['saved'].values()) == set(data['ids'])


def test_auto_full_make_image_uses_distinct_chats_and_keeps_existing_media(tmp_path):
    from test_video_auto_scene_provider import batch_scope
    scope, paths = batch_scope(tmp_path, 2)
    scope['image_provider_for'] = lambda stage:'gpt_web'
    scope['IMAGES_PER_CHAT'] = 12
    cursors=[]
    barrier=threading.Barrier(2)
    def generate(prompt, **kwargs):
        cursors.append(kwargs['conversation_state'])
        assert kwargs['parallel_images'] and kwargs['temporary_chat']
        assert kwargs['conversation_save_fn'] is None
        assert kwargs['ref_images'][0] == base64.b64encode(Path(paths[-1]).read_bytes()).decode()
        barrier.wait(timeout=3)
        target=tmp_path/(kwargs['name_hint']+'-output.png')
        target.write_text(prompt)
        return str(target)
    scope['runtime']['_imgmod'] = SimpleNamespace(generate_image=generate)
    scope['attachments_for'] = lambda scene,limit=None: paths[:2]
    scope['archive_scene_image'] = lambda p:pytest.fail('existing media must remain')
    load(scope,'make_image')
    load(scope,'run_gpt_scenes')
    scope['stage_images']()
    assert len(cursors)==2 and cursors[0] is not cursors[1]
    assert all(Path(p).exists() for p in paths)


def test_usage_parallel_writers_do_not_lose_counts(tmp_path, monkeypatch):
    import snapgen_chrome_relay as R
    monkeypatch.setattr(R, '_usage_file', lambda:tmp_path/'usage.json')
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _:R.count_pictures('test-account', '', 1),range(40)))
    assert len(json.loads((tmp_path/'usage.json').read_text())['test-account']['made'])==40


def test_failed_image_drains_other_submitted_image_without_starting_third():
    barrier=threading.Barrier(2)
    started,saved=[],[]
    def work(i):
        started.append(i)
        barrier.wait(timeout=3)
        if i==0:
            raise RuntimeError('unknown result')
        time.sleep(.05)
        return 'second-image'
    with pytest.raises(RuntimeError,match='unknown result'):
        N._run_image_jobs(range(4),work,lambda i,result,error:saved.append((i,result)),
                          lambda:None,max_workers=2)
    assert sorted(started)==[0,1]
    assert (1,'second-image') in saved

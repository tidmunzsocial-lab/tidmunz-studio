"""Production planning must not retain the previous history-upload status."""
import json
from types import SimpleNamespace

from test_video_auto_scene_provider import N, load


def test_plan_requests_and_retry_show_current_stage_without_resetting_progress(tmp_path):
    (tmp_path/'transcript.json').write_text('[]')
    events=[]
    project={'context':{},'duration':20,'direction':{},'aspect':'16:9'}
    noop=lambda *a,**k:None
    def chat(prompt):
        assert 'ส่งบทและ Context' not in events[-1][2]
        return '{}'
    def retries(label,fn):
        fn()  # A retry must refresh its current label, too.
        return fn()
    def plan(*args,ask=None,progress=None,out=None,**kwargs):
        # Production passes ask positionally.
        ask=args[4]
        ask('director')
        out.append({'prompt':'saved'})
        progress(1,2,0)
        ask('next batch')
        assert events[-1][1]==.5
        assert 'บันทึกแล้ว 1 ฉาก' in events[-1][2]
    scope=dict(vars(N),state={'project':project,'folder':str(tmp_path)},video_mode=True,
        check_script_matches_audio=noop,ensure_story_in_history=noop,
        set_progress=lambda *a:events.append(a),repair_transcript=lambda a,b:(a,False),
        story_script=lambda:'story',story_time_note=lambda:'',check_stop=noop,
        chat=chat,with_retries=retries,plan_video=plan,script_dialogues=lambda s:[],
        attachment_names=lambda:[],desired_aspect=lambda:'16:9',economy_on=lambda:False,
        prices={'data':{}},muse_scenery_price_allowed=lambda *a:False,
        apply_selected_video_model=noop,save_project=noop,log=noop,
        cinematographer_pass=noop,clip_summary=lambda scenes:'ok',ui=noop,refresh_table=noop)
    load(scope,'stage_plan')()
    assert events[0][2]=='GPT รับบทและ Context แล้ว — เตรียมวางแผนฉาก'
    assert sum('คำขอที่ 1' in e[2] for e in events)==2
    assert sum('คำขอที่ 2' in e[2] for e in events)==2


def test_non_json_plan_reply_is_repaired_in_same_story_chat(tmp_path):
    (tmp_path/'transcript.json').write_text('[]')
    events=[]; calls=[]; logs=[]; outputs=[]
    project={'context':{'story':{'title':'current story'}},'conversation':{'conversation_id':'story-chat'},
             'history_seeded':True,'duration':20,'direction':{},'aspect':'16:9','scenes':[]}
    noop=lambda *a,**k:None
    def chat(prompt):
        calls.append((prompt,project['conversation']['conversation_id']))
        return 'This is not JSON' if len(calls)==1 else '{"scenes": []}'
    def retries(_label, action): return action()
    def plan(*args,progress=None,out=None,**kwargs):
        ask=args[4]
        result=ask('write a fresh scene plan')
        outputs.append(result)
        out.append({'prompt':'new scene'})
        progress(1,1,0)
    scope=dict(vars(N),state={'project':project,'folder':str(tmp_path)},video_mode=True,
        check_script_matches_audio=noop,ensure_story_in_history=noop,
        set_progress=lambda *a:events.append(a),repair_transcript=lambda a,b:(a,False),
        story_script=lambda:'story',story_time_note=lambda:'',check_stop=noop,
        chat=chat,with_retries=retries,plan_video=plan,script_dialogues=lambda s:[],
        attachment_names=lambda:[],desired_aspect=lambda:'16:9',economy_on=lambda:False,
        prices={'data':{}},muse_scenery_price_allowed=lambda *a:False,
        apply_selected_video_model=noop,save_project=noop,log=logs.append,
        cinematographer_pass=noop,clip_summary=lambda scenes:'ok',ui=noop,refresh_table=noop)
    load(scope,'stage_plan')()
    assert len(calls)==2
    assert calls[0][0]=='write a fresh scene plan'
    assert 'JSON อย่างเดียว' in calls[1][0]
    assert calls[0][1]==calls[1][1]=='story-chat'
    assert outputs==[{'scenes':[]}]
    assert project['context']=={'story':{'title':'current story'}}
    assert project['scenes']==[{'prompt':'new scene'}]
    assert any('จัดคำตอบเป็น JSON' in event[2] for event in events)
    assert any('อัตโนมัติ' in message for message in logs)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def segs(*pairs):
    return [{"start": s, "end": e, "text": f"t{s}"} for s, e in pairs]


def test_plan_windows_split_by_length():
    windows = N.plan_windows(segs((0, 100), (100, 190), (190, 300), (300, 320)), window=180)
    assert [[s["start"] for s in w] for w in windows] == [[0, 100], [190, 300]] or len(windows) == 2


def test_snap_starts_to_sentences_and_keep_window_start():
    assert N.snap_starts([12.9, "x", 31], [0, 10, 13, 30], 0) == [0, 13, 30]
    assert N.snap_starts([], [50, 60], 50) == [50]


def test_durations_and_xfade_total_length():
    durs = N.segment_durations([0, 10, 25], 40)
    assert durs == [10, 15, 15]
    lengths = [d + N.CROSSFADE for d in durs[:-1]] + [durs[-1]]
    graph, total = N.xfade_graph(lengths)
    assert abs(total - 40) < 1e-6
    assert graph.count("xfade") == 2 and graph.endswith("[vout]")


def test_json_reply_inside_markdown():
    assert N.parse_json_reply('ok ```json\n{"scenes": []}\n```') == {"scenes": []}


def test_ass_contains_dialogue_lines():
    text = N.build_ass([{"start": 1.0, "end": 2.5, "text": "สวัสดี {x}"}], 1920, 1080)
    assert "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,สวัสดี (x)" in text


def test_character_description_skips_unknown():
    assert N.character_description({"อายุ": "50", "ใบหน้า": "ไม่ระบุ", "เสื้อผ้า": "เสื้อม่อฮ่อม"}) == "50 เสื้อม่อฮ่อม"


def test_correct_with_script_fixes_words_and_drops_junk():
    script = "เขาเรียนจบชั้นประถมศึกษาปีที่ 6 ก็ไม่เรียนต่อ ซ้ำยังไม่เคยคิดทำบุญ หรือทำความดีใดๆ"
    heard = [{"start": 0, "end": 3, "text": "เขาเรียนจบชั้นประสงค์ศึกษาปีที่ 6 ก็ไม่เรียนต่อ"},
             {"start": 3, "end": 5, "text": "ซ้ำยังไม่เคยคิดทำบุญaspll.ch"},
             {"start": 5, "end": 6, "text": "hello world totally different"}]
    fixed = N.correct_with_script(heard, script)
    assert fixed[0]["text"] == "เขาเรียนจบชั้นประถมศึกษาปีที่ 6 ก็ไม่เรียนต่อ"
    assert fixed[1]["text"] == "ซ้ำยังไม่เคยคิดทำบุญ"
    assert fixed[2]["text"] == "hello world totally different"


def test_limit_scenes_caps_count_by_merging_shortest():
    scenes = [{"start": t} for t in (0, 10, 11, 30, 31.5, 50)]
    out = N.limit_scenes(scenes, 4, 60)
    assert [s["start"] for s in out] == [0, 11, 31.5, 50]  # short scenes merge into the previous one
    assert N.limit_scenes(scenes, 10, 60) == scenes


def test_refs_only_for_individuals_who_appear_in_scenes():
    context = {"characters": [
        {"name": "นายจำนง", "importance": "main"},
        {"name": "จุรี"},
        {"name": "จรรยา"},                       # never shown
        {"name": "ชาวบ้าน", "is_group": True},   # crowd
        {"name": "ทหารนาคา"},                     # group by name
    ]}
    scenes = [{"characters": ["จุรี"]}, {"characters": ["นายจำนง", "ชาวบ้าน"]},
              {"characters": ["นายจำนง", "ทหารนาคา"]}, {"characters": []}]
    needed = N.characters_needing_refs(context, scenes)
    assert [(c["name"], n) for c, n in needed] == [("นายจำนง", 2), ("จุรี", 1)]


def test_context_requests_carry_story_and_keep_names():
    assert "FULL STORY:\nบททดสอบ" in N.analysis_request("บททดสอบ")
    text = N.context_from_analysis_request({"characters": [{"name": "นายจำนง"}]})
    assert "STORY_ANALYSIS_JSON" in text and "นายจำนง" in text and "is_group" in text


def test_one_project_folder_per_story(tmp_path):
    import json
    base = tmp_path / "เล่าภาพ"
    a = tmp_path / "A" / "บท.docx"
    b = tmp_path / "B" / "บท.docx"
    first = N.project_folder_for(base, str(a), "เรื่องแรก")
    first.mkdir(parents=True)
    (first / "project.json").write_text(json.dumps({"script": str(a), "script_hash": N.script_hash("เรื่องแรก")}), encoding="utf-8")
    assert N.project_folder_for(base, str(a), "เรื่องแรก แก้คำนิดหน่อย").name == "บท (2)"  # edited source gets a new revision
    assert N.project_folder_for(base, str(b), "เรื่องแรก") == first                     # same story moved
    other = N.project_folder_for(base, str(b), "เรื่องที่สองคนละเรื่อง")
    assert other.name == "บท (2)"                                                     # same name, new story


def test_split_long_scenes_for_short_clips():
    scenes = [{"start": 0, "prompt": "a", "video_prompt": "va", "motion": "zoom_in"},
              {"start": 20, "prompt": "b", "motion": "pan_left"}]
    out = N.split_long_scenes(scenes, 26, 6)
    assert [s["start"] for s in out] == [0, 5, 10, 15, 20]   # 20 s -> 4 clips, 6 s stays one
    assert "ช็อตต่อเนื่อง 2/4" in out[1]["prompt"] and out[1]["motion"] != out[0]["motion"]
    assert out[4]["prompt"] == "b"


def test_clip_fit_filter_trims_or_slows_then_holds():
    assert "setpts=1.0000*PTS" in N.clip_fit_filter(8, 6, 1920, 1080) and "tpad" not in N.clip_fit_filter(8, 6, 1920, 1080)
    slow = N.clip_fit_filter(6, 12, 1920, 1080)
    assert "setpts=1.6000*PTS" in slow and "tpad=stop_mode=clone" in slow and "trim=duration=12.000" in slow


def test_pick_clip_cheapest_that_covers_the_shot():
    assert N.pick_clip(4, False, True) == ("vela-ai-video", 5, False)
    assert N.pick_clip(9, True, True) == ("vela-ai-video", 5, True)      # vela 5 s + Slow 2x = 10 s
    assert N.pick_clip(9, False, True) == ("grok-lower", 10, False)      # no slow → vela too short
    assert N.pick_clip(6.5, False, False) == ("grok-lower", 6, False)    # small stretch is fine
    assert N.pick_clip(11, True, False) == ("grok-lower", 6, True)       # 6 s ×2 cheaper than 15 s
    assert N.pick_clip(11.5, False, False) == ("grok-lower", 10, False)


def test_video_auto_splits_long_shots_and_assigns_clips():
    scenes = [{"start": 0, "prompt": "a", "motion": "zoom_in", "cheap": True},
              {"start": 30, "prompt": "b", "motion": "pan_left", "slow": True}]
    out = N.split_long_scenes(scenes, 49, 0, limit_for=N.clip_limit)
    assert [s["start"] for s in out] == [0, 10, 20, 30]                  # 30 s → 3 shots; slow 19 s stays one
    N.assign_clips(out, 49)
    assert out[0]["clip_model"] == "grok-lower" and out[0]["clip_seconds"] == 10
    assert (out[3]["clip_seconds"], out[3]["clip_slow"]) == (10, True)
    out[0]["clip_fallback"] = True
    N.assign_clips(out, 49)
    assert out[0]["cheap"] is False


def test_video_shots_cut_at_sentences():
    segs = [{"start": 0, "end": 4, "text": "a"}, {"start": 4, "end": 9, "text": "b"},
            {"start": 9, "end": 16, "text": "c"}, {"start": 16, "end": 30, "text": "d"},
            {"start": 30, "end": 32, "text": "e"}]
    shots = N.video_shots(segs)
    assert [(s["start"], s["end"], s["text"]) for s in shots] == [(0.0, 9, "a b"), (9, 16, "c"), (16, 30, "d"), (30, 32, "e")]


def test_plan_video_asks_again_for_skipped_shots():
    segs = [{"start": i * 8.0, "end": i * 8.0 + 8, "text": f"t{i}"} for i in range(3)]
    calls = []

    def ask(prompt):
        if "คุณคือผู้กำกับ" in prompt:  # director pass
            return {"look": {"palette": "ฟ้าเข้ม"}, "sequences": [{"shots": [1, 3], "name": "ทะเล"}]}
        calls.append(prompt)
        if len(calls) == 1:  # GPT skips shot 2 the first time
            return {"scenes": [{"shot": 1, "prompt": "p1"}, {"shot": 3, "prompt": "p3", "cheap": True}]}
        return {"scenes": [{"shot": 2, "prompt": "p2", "slow": "true"}]}
    scenes = N.plan_video(segs, 24, [], "", ask)
    assert [s["prompt"] for s in scenes] == ["p1", "p2", "p3"] and len(calls) == 2
    assert "[2]" in calls[1] and "[1]" not in calls[1] and "ฟ้าเข้ม" in calls[1]   # direction reaches shots
    assert scenes[1]["slow"] and scenes[2]["cheap"]
    assert (scenes[2]["clip_model"], scenes[2]["clip_seconds"]) == ("grok-lower", 10)  # 8 s: vela 5 s is too short


def test_dialogue_gets_its_own_exact_shot_without_slow_motion():
    script = "เขาลุกขึ้น\nนาคประหลาด : “ ไม่ ข้าจะไม่ทำ ”\nแต่ไม่ได้ผล"
    words = [[10.0, 10.5, "ไม่"], [11.0, 12.0, "ข้าจะไม่ทำ"], [13.0, 13.5, "แต่"], [13.5, 15.0, "ไม่ได้ผล"]]
    segs = [{"start": 0.0, "end": 9.0, "text": "เขาลุกขึ้น"},
            {"start": 10.0, "end": 15.0, "text": "ไม่ ข้าจะไม่ทำ ” แต่ไม่ได้ผล", "words": words}]
    pieces = N.split_dialogue(segs, script)
    spoken = [p for p in pieces if p.get("dialogue")]
    assert len(spoken) == 1 and spoken[0]["dialogue"] == "นาคประหลาด"
    assert spoken[0]["start"] == 10.0 and spoken[0]["end"] == 13.0 and spoken[0]["text"] == "ไม่ ข้าจะไม่ทำ"
    shots = N.video_shots(pieces)
    assert [s.get("dialogue") for s in shots] == [None, "นาคประหลาด", None]   # never joined with narration
    scenes = N.plan_video(segs, 15, ["นาคประหลาด"], "", lambda _p: {"scenes": [
        {"shot": n, "prompt": f"p{n}", "slow": True, "cheap": True} for n in (1, 2, 3)]}, script=script)
    talk = scenes[1]
    assert talk["dialogue"] and not talk["slow"] and not talk["clip_slow"] and talk["clip_model"] == "grok-lower"


def test_script_audio_match_tells_another_story():
    script = "ท่ามกลางแสงแดดจ้า ที่ปกคลุมอยู่เหนือมหาสมุทรกว้างใหญ่แห่งหนึ่ง จู่ๆ แสงแดดจ้านั้นก็หายวับไปกับตา"
    same = [{"text": "ท่ามกลางแสงแดดจ้าที่ปกคลุมอยู่เหนือมหาสมุทร"}, {"text": "จู่ๆ แสงแดดจ้านั้นก็หายวับไป"}]
    other = [{"text": "หลังจากที่กามณิตหนุ่มได้สิ้นใจจากโลกมนุษย์ ก็มาเกิดกลางดอกบัวสวรรค์"}]
    assert N.script_audio_match(same, script) > 0.9
    assert N.script_audio_match(other, script) < 0.6


def test_transitions_dissolve_in_scene_and_dip_to_black_on_new_place():
    scenes = [{"start": 0, "location": "ใต้น้ำ"}, {"start": 6, "location": "ใต้น้ำ"},
              {"start": 12, "location": "ป่า"}, {"start": 15, "location": "ป่า", "transition": "cut"}]
    kinds = [N.transition_into(scenes[i - 1] if i else None, s) for i, s in enumerate(scenes)]
    assert kinds == ["dissolve", "dissolve", "fadeblack", "cut"]
    durs = N.segment_durations([s["start"] for s in scenes], 20)
    over = [N.TRANSITIONS[kinds[i + 1]][1] for i in range(len(scenes) - 1)] + [0.0]
    graph, total = N.xfade_graph([d + o for d, o in zip(durs, over)], kinds=kinds)
    assert abs(total - 20) < 1e-6 and "transition=fadeblack:duration=1.2" in graph


def test_continuity_carries_wounds_to_later_shots_of_that_character():
    scenes = [{"characters": ["นาค"]}, {"characters": ["นาค", "ราชา"]}, {"characters": ["ราชา"]},
              {"characters": []}, {"characters": ["นาค"]}]
    entries = [{"character": "นาค", "from_shot": 2, "to_shot": 5, "state": "แผลดาบที่ลำตัวซ้าย มีเลือด"},
               {"character": "ราชา", "from_shot": 3, "to_shot": 3, "state": "เปียกน้ำ"}]
    N.apply_continuity(scenes, entries)
    assert "continuity" not in scenes[0]                                   # before the wound
    assert "แผลดาบ" in scenes[1]["continuity"]
    assert scenes[2]["continuity"] == "ราชา: เปียกน้ำ"                      # นาค not in this shot
    assert "continuity" not in scenes[3] and "แผลดาบ" in scenes[4]["continuity"]   # empty shot: nothing
    assert "continuity" in N.continuity_request([(1, scenes[0])], ["นาค"])


def test_storyboard_groups_follow_sequences_and_crop_3x3(tmp_path):
    scenes = [{"shot_no": n} for n in (1, 2, 3, 4, 4, 5)] + [{"shot_no": 6} for _ in range(11)]
    direction = {"sequences": [{"shots": [1, 3]}, {"shots": [4, 5]}, {"shots": [6, 6]}]}
    groups = N.board_groups(scenes, direction)
    assert groups[:2] == [[0, 1, 2], [3, 4, 5]]                         # one sheet per sequence
    assert [len(g) for g in groups[2:]] == [9, 2]                        # long sequence split at 9
    assert [len(g) for g in N.board_groups([{}] * 12, None)] == [9, 3]   # older plans: runs of 9
    from PIL import Image
    sheet = Image.new("RGB", (300, 300))
    for k in range(9):
        r, c = divmod(k, 3)
        sheet.paste((k * 25, 0, 0), (c * 100, r * 100, c * 100 + 100, r * 100 + 100))
    sheet.save(tmp_path / "s.png")
    outs = [tmp_path / f"p{k}.png" for k in range(4)]
    N.crop_board(tmp_path / "s.png", 4, outs)
    assert [Image.open(p).getpixel((5, 5))[0] for p in outs] == [0, 25, 50, 75]
    assert "3 แถว x 3 คอลัมน์" in N.board_request([(1, {"prompt": "ก"})], "9:16")

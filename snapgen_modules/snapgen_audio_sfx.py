# -*- coding: utf-8 -*-
"""Fail-closed, offline video-clip effects selection and lossless narration mux.

- No clip speech, singing, vocalizations or music is intentionally mixed.
- YAMNet AudioSet + Silero VAD are used to screen clips. If models fail, skip
  all clip effects rather than adding uncertain speech or music.
- Only high-confidence non-vocal effect windows are selected.
- The original WAV narration is never resampled, normalized or compressed.
- For mixed exports, a *second* ALAC audio stream retains the unmodified WAV.
  The first ALAC stream is the effect mix at a conservative gain.
The models are classifiers, not perfect source separators. Ambiguous content
is omitted; this does not certify that classifiers never make mistakes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import csv
import hashlib
import math
import os
import subprocess
import wave

_MODEL_FOLDER = Path(__file__).resolve().parent.parent / "snapgen_data" / "tools" / "audio_sfx_models"
_MODEL_SHA256 = {
    "yamnet.onnx": "9a6aef46391df10a4ff804ea196266855a532a200ec13894024da24e16aaf7b1",
    "silero_vad.onnx": "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
}
_RATE = 48000
_ANALYSIS_RATE = 16000
_VOICE_THRESHOLD = 0.055
_MUSIC_THRESHOLD = 0.045
_VAD_THRESHOLD = 0.20
_EVENT_THRESHOLD = 0.17
_EFFECT_GAIN = 0.35
_MAX_AUDIO_PER_SCENE = 12.0


def _valid_model(path: Path, digest: str) -> bool:
    if not path.is_file():
        return False
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest() == digest


@lru_cache(maxsize=1)
def _load():
    import numpy as np
    import onnxruntime as ort
    for name, digest in _MODEL_SHA256.items():
        if not _valid_model(_MODEL_FOLDER / name, digest):
            raise RuntimeError("Audio classifier unavailable or checksum mismatch: " + name)
    csvfile = _MODEL_FOLDER / "yamnet_class_map.csv"
    if not csvfile.is_file():
        raise RuntimeError("Audio event labels unavailable")
    with csvfile.open("r", encoding="utf-8-sig", newline="") as f:
        labels = [r["display_name"] for r in csv.DictReader(f)]
    if len(labels) != 521 or labels[0] != "Speech" or labels[132] != "Music":
        raise RuntimeError("Unexpected YAMNet class map")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    yamnet = ort.InferenceSession(str(_MODEL_FOLDER / "yamnet.onnx"),
                                  providers=["CPUExecutionProvider"], sess_options=opts)
    vad = ort.InferenceSession(str(_MODEL_FOLDER / "silero_vad.onnx"),
                               providers=["CPUExecutionProvider"], sess_options=opts)
    # Avoid silence, plain recording context, environment context and other
    # non-specific classes. Concrete events (steps, rustling, water, etc.) stay.
    not_event = {"Silence", "Field recording", "Environmental noise", "Sound effect",
                 "Outside, rural or natural", "Outside, urban or manmade",
                 "Inside, small room", "Inside, large room or hall",
                 "Domestic sounds, home sounds", "Noise", "White noise",
                 "Pink noise", "Static", "Hiss"}
    forbidden = set(range(0, 48)) | {65} | set(range(132, 277))
    events = [i for i, label in enumerate(labels)
              if i not in forbidden and label not in not_event]
    return np, yamnet, vad, labels, events, sorted(forbidden)


def _decode(ffmpeg, clip: str, *, duration: float, rate: int, channels: int):
    import numpy as np
    if not Path(clip).is_file():
        return np.array([], dtype=np.float32)
    p = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", clip,
         "-map", "0:a:0", "-t", f"{duration:.4f}", "-ac", str(channels),
         "-ar", str(rate), "-f", "f32le", "pipe:1"],
        capture_output=True, timeout=24)
    if p.returncode:
        return np.array([], dtype=np.float32)
    x = np.frombuffer(p.stdout, dtype="<f4").copy()
    if channels == 2:
        x = x[:len(x) - len(x) % 2].reshape((-1, 2))
    return x


def _vad_max_probability(audio, session, np):
    # Recurrent Silero v6, 512 new samples + 64 context samples at 16 kHz.
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    max_prob = 0.0
    n = 512
    total = int(math.ceil(len(audio) / n) * n)
    padded = np.pad(audio, (0, total - len(audio))).astype(np.float32, copy=False)
    for start in range(0, total, n):
        frame = padded[start:start+n].reshape((1, n))
        batch = np.concatenate((context, frame), axis=1)
        outputs = session.run(None, {"input":batch, "state":state,
                                    "sr":np.array(16000, dtype=np.int64)})
        probability, state = outputs
        max_prob = max(max_prob, float(probability.max()))
        context = frame[:, -64:].copy()
    return max_prob


def _analyze_one(scene, ffmpeg, duration, runtime):
    np, yamnet, vad, labels, events, _ = runtime
    path = str(scene.get("clip") or "")
    source_length = max(0.0, min(float(duration), _MAX_AUDIO_PER_SCENE))
    if not path or source_length < 0.8:
        return {"reason":"missing_or_short_clip"}
    try:
        mono = _decode(ffmpeg, path, duration=source_length, rate=16000, channels=1)
    except (OSError, subprocess.TimeoutExpired):
        return {"reason":"audio_read_failed"}
    if len(mono)<16000:
        return {"reason":"no_audio"}
    if not np.all(np.isfinite(mono)):
        return {"reason":"invalid_audio"}
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    if rms < 0.002:
        return {"reason":"almost_silent"}
    try:
        scores = yamnet.run(None, {"waveform:0":mono.astype(np.float32,copy=False)})[0]
    except Exception:
        return {"reason":"model_error"}
    if scores.ndim!=2 or scores.shape[1]!=521:
        return {"reason":"unexpected_scores"}
    if float(np.max(scores[:,list(range(48))+[65]])) >= _VOICE_THRESHOLD:
        return {"reason":"voice_detected"}
    if float(np.max(scores[:,132:277])) >= _MUSIC_THRESHOLD:
        return {"reason":"music_detected"}
    try:
        vad_max = _vad_max_probability(mono, vad, np)
    except Exception:
        return {"reason":"vad_unavailable"}
    if vad_max >= _VAD_THRESHOLD:
        return {"reason":"speech_vad_detected"}
    peak_events = scores[:,events].max(axis=1)
    # A near-silent generated clip must not add an unrelated heartbeat.
    strongest = events[int(np.argmax(scores[:,events].max(axis=0)))]
    if labels[strongest] in ("Heart sounds, heartbeat", "Heart murmur"):
        action = str(scene.get("video_prompt") or "").split(
            "This audio rule overrides", 1)[0].lower()
        if not any(term in action for term in ("heartbeat", "heart beats", "หัวใจ", "ชีพจร", "ใจเต้น")):
            return {"reason":"sound_unrelated_to_visible_action"}
    if float(peak_events.max()) < _EVENT_THRESHOLD:
        return {"reason":"no_confident_effect"}
    # YAMNet emits predictions about every 0.48 seconds. Keep only concrete
    # event frames; do not copy an entire video's audio to the soundtrack.
    safe_frame = peak_events>=_EVENT_THRESHOLD
    # Silence often looks like an event; also check for actual sound energy.
    mask = np.zeros(len(mono), dtype=np.float32)
    for idx,yes in enumerate(safe_frame):
        if not yes:
            continue
        start=int(idx*.48*_ANALYSIS_RATE)
        end=min(len(mask),int((idx+1)*.48*_ANALYSIS_RATE))
        if end<=start:
            continue
        if float(np.sqrt(np.mean(np.square(mono[start:end],dtype=np.float64))))<0.002:
            continue
        mask[start:end]=1.0
    if float(mask.mean()) < 0.07:
        return {"reason":"no_audible_effect_window"}
    # Expand to the 48 kHz stereo source and fade each edge to prevent clicks.
    try:
        stereo=_decode(ffmpeg,path,duration=source_length,rate=48000,channels=2)
    except Exception:
        return {"reason":"source_effect_read_failed"}
    if not len(stereo):
        return {"reason":"source_effect_read_failed"}
    # 16k -> 48k sample alignment, bounded by real clip duration.
    gate=np.repeat(mask,3)[:len(stereo)]
    if len(gate)<len(stereo):
        gate=np.pad(gate,(0,len(stereo)-len(gate)))
    # Two 45 ms ramps around on/off gates suppress hard transitions.
    transition=int(.045*48000)
    # O(N) moving-average fade; np.convolve would be O(N*window) for each clip.
    window=2*transition+1
    padded=np.pad(gate,(transition,transition))
    prefix=np.concatenate(([0.0],np.cumsum(padded,dtype=np.float64)))
    gate=((prefix[window:]-prefix[:-window])/window).astype(np.float32)
    if len(gate)!=len(stereo):
        return {"reason":"gate_shape_mismatch"}
    sound=stereo*gate[:,None]*_EFFECT_GAIN
    maxabs=float(np.max(np.abs(sound)))
    if maxabs>.065:
        sound*=.065/maxabs
    sound=np.clip(sound,-1.0,1.0)
    peak=float(np.max(np.abs(sound)))
    if peak < .0008:
        return {"reason":"effect_below_audibility"}
    return {"reason":"included","signal":(sound*32767).astype(np.int16),
            "event_frames":int(safe_frame.sum()),"rms":rms,"peak":peak}


def build_effect_track(ffmpeg, scenes, durations, total_seconds, render_folder, *,
                       log=lambda text:None, check_stop=lambda:None, audit_only=False):
    """Return lossless stereo WAV effect track or None.

    Never mixes an unclassified clip. If models cannot run, original narration
    continues unmodified. Caller need not prompt user or choose sound mode.
    """
    import numpy as np
    try:
        runtime = _load()
    except Exception as e:
        log("เสียงคลิป: ตัวแยกเสียงพูด/เพลงไม่พร้อม จึงไม่ผสมเสียงคลิปเพื่อป้องกันเสียงคนหรือเพลง (" +
            type(e).__name__ + ")")
        return None, {"included":0,"rejected":{"classifier_unavailable":len(scenes)}}
    candidates=[]
    counts={}
    count=min(len(scenes),len(durations))
    for i in range(count):
        check_stop()
        scene=scenes[i]
        # Explicit user exclusion of dialogue and source-clip human voices.
        # Speech and music screening runs even for visually silent dialogue.
        result=_analyze_one(scene,ffmpeg,durations[i],runtime)
        reason=result.get("reason","unknown")
        counts[reason]=counts.get(reason,0)+1
        if reason=="included":
            candidates.append((float(scene.get("start") or 0),result["signal"],i))
    report={"included":len(candidates),"rejected":{k:v for k,v in counts.items() if k!="included"}}
    if audit_only or not candidates:
        log("เสียงเอฟเฟกต์: ผ่านตัวกรอง "+str(len(candidates))+"/"+str(count)+
            " ช็อต (ไม่ผสมเสียงคลิปที่พบเสียงพูด/เพลงหรือจำแนกไม่ได้)")
        return None, report
    total_frames=int(round(float(total_seconds)*_RATE))
    if total_frames<=0 or total_frames>_RATE*36000:
        raise ValueError("invalid final narration duration")
    mix=np.zeros((total_frames,2),dtype=np.int16)
    for start,signal,i in candidates:
        offset=int(round(start*_RATE))
        if offset<0 or offset>=total_frames:continue
        segment=signal[:min(len(signal),total_frames-offset)]
        if not len(segment):continue
        buf=mix[offset:offset+len(segment)].astype(np.int32)
        buf+=segment.astype(np.int32)
        mix[offset:offset+len(segment)]=np.clip(buf,-32768,32767).astype(np.int16)
    output=Path(render_folder)/"scene_effects_verified_no_voice_no_music.wav"
    with wave.open(str(output),"wb") as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(_RATE)
        out.writeframes(mix.tobytes())
    log("เสียงเอฟเฟกต์: ผ่านตัวกรอง "+str(len(candidates))+"/"+str(count)+
        " ช็อต, กรองเสียงพูด/ร้องเพลง/ดนตรีออกจากแหล่งคลิป; แทร็กบรรยายเดิมไม่ถูกแก้")
    return output, report


def lossless_audio_args(original_audio: str, effect_track, *, label="Original Narration PCM"):
    """Generate ffmpeg mapping/codec args for the mux; no bitrate downsampling."""
    args=["-i",str(original_audio)]
    if effect_track is None:
        return args, ["-map","0:v:0","-map","1:a:0",
                      "-c:v","copy","-c:a","alac",
                      "-metadata:s:a:0","title=Original narration - lossless",
                      "-disposition:a:0","default","-movflags","+faststart"]
    args.extend(["-i",str(effect_track)])
    # Primary: original narration at 100% gain + quiet effect-only samples.
    # Secondary: exact lossless original WAV for restoration and QA.
    filters=("[1:a:0]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[n];"
             "[2:a:0]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[s];"
             "[n][s]amix=inputs=2:duration=first:normalize=0[mix]")
    return args, ["-filter_complex",filters,
                  "-map","0:v:0","-map","[mix]","-map","1:a:0",
                  "-c:v","copy","-c:a","alac",
                  "-metadata:s:a:0","title=Narration + verified effects - lossless",
                  "-metadata:s:a:1","title=Original narration bit-exact - lossless",
                  "-disposition:a:0","default","-disposition:a:1","0",
                  "-movflags","+faststart"]


def verify_original_pcm(ffmpeg, original_wav, exported_mp4, track_index=0):
    """Byte-exact 48k stereo PCM comparison after lossless ALAC decode."""
    import hashlib
    import wave
    with wave.open(str(original_wav), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (48000,2,2):
            raise RuntimeError("Original narration format differs: require 48k stereo PCM 16")
        expected=wav.getnframes()*4
        h=hashlib.sha256()
        while True:
            buf=wav.readframes(262144)
            if not buf:break
            h.update(buf)
        original=h.hexdigest()
    proc=subprocess.Popen(
        [ffmpeg,"-hide_banner","-loglevel","error","-i",str(exported_mp4),
         "-map",f"0:a:{int(track_index)}","-c:a","pcm_s16le",
         "-ac","2","-ar","48000","-f","s16le","pipe:1"],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    audio_hash=hashlib.sha256()
    size=0
    while True:
        buf=proc.stdout.read(1024*1024)
        if not buf:break
        audio_hash.update(buf);size+=len(buf)
    diagnostic=proc.stderr.read().decode("utf8","replace")
    if proc.wait(timeout=20)!=0:
        raise RuntimeError("Lossless QA decode failed: "+diagnostic[-280:])
    if size!=expected or audio_hash.hexdigest()!=original:
        raise RuntimeError("Original narration PCM not bit-exact after export")
    return {"bit_exact":True,"pcm_sha256":original,
            "source_pcm_bytes":expected,"checked_track":int(track_index)}

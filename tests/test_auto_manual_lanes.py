import threading
from concurrent.futures import ThreadPoolExecutor

from test_video_auto_scene_provider import N, load


def test_independent_lanes_keep_busy_until_both_finish_and_block_same_shot():
    state = {"busy": False, "stop": False, "lock": threading.RLock()}
    scope = dict(vars(N), state=state)
    reserve = load(scope, "reserve_manual_lane")
    release = load(scope, "release_manual_lane")
    assert reserve("images", [0, 1])
    assert not reserve("videos", [1, 2])
    assert reserve("videos", [2, 3])
    assert not reserve("images", [4])
    release("images")
    assert state["busy"]
    assert reserve("images", [4, 5])
    release("videos")
    assert state["busy"]
    release("images")
    assert not state["busy"]
    state["busy"] = True
    assert not reserve("images", [0])  # Full pipeline still owns the project.


def test_two_image_and_two_video_jobs_overlap_without_raising_local_limit():
    state = {"busy": False, "stop": False, "lock": threading.RLock()}
    scope = dict(vars(N), state=state)
    reserve = load(scope, "reserve_manual_lane")
    release = load(scope, "release_manual_lane")
    cloud_barrier = threading.Barrier(4)
    local_lock = threading.Lock()
    active = {"images": 0, "videos": 0, "local": 0}
    peak = active.copy()

    def job(kind):
        with state["lock"]:
            active[kind] += 1
            peak[kind] = max(peak[kind], active[kind])
        cloud_barrier.wait(3)
        with local_lock:
            with state["lock"]:
                active["local"] += 1
                peak["local"] = max(peak["local"], active["local"])
                active["local"] -= 1
        with state["lock"]:
            active[kind] -= 1

    assert reserve("images", [0, 1]) and reserve("videos", [2, 3])
    with ThreadPoolExecutor(max_workers=2) as images, ThreadPoolExecutor(max_workers=2) as videos:
        futures = [images.submit(job, "images") for _ in range(2)]
        futures += [videos.submit(job, "videos") for _ in range(2)]
        for future in futures:
            future.result()
    release("images")
    release("videos")
    assert peak == {"images": 2, "videos": 2, "local": 1}
    assert not state["busy"]

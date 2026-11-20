"""``upload.queue`` 的 15 个红测试。

覆盖 10 个缺陷各 1 条，外加 5 条组合/边界：
空队列规划、单任务恰好等于预算、零预算、重复 id 入队、批量成功不改顺序。

初始骨架下 15 条全部因 ``NotImplementedError`` 变红，不允许出现
collection / import / syntax error。本文件是评测基线，不可修改。
"""

import pytest

from upload.queue import (
    UploadError,
    dequeue,
    enqueue,
    estimate_frames,
    expire,
    plan_frame,
    reorder,
    upload_batch,
    validate,
)


def task(task_id, size, priority, deadline):
    """构造一个合法任务（``size`` 即字节数）。"""
    return {"id": task_id, "bytes": size, "priority": priority, "deadline": deadline}


def ids(queue):
    """取队列里的任务 id 顺序。"""
    return [item["id"] for item in queue]


def test_enqueue_keeps_priority_order_and_fifo_for_ties():
    """缺陷 1：同优先级必须按入队顺序稳定排列，不能每次顺序都变。"""
    queue = []
    enqueue(queue, task("low", 1, 1, 100))
    enqueue(queue, task("high-a", 1, 5, 100))
    enqueue(queue, task("high-b", 1, 5, 100))
    enqueue(queue, task("mid", 1, 3, 100))

    assert ids(queue) == ["high-a", "high-b", "mid", "low"]


def test_plan_frame_never_exceeds_byte_budget():
    """缺陷 2：本帧总字节不得超过预算，装不下的任务顺延。"""
    queue = []
    enqueue(queue, task("a", 6, 5, 100))
    enqueue(queue, task("b", 6, 4, 100))

    picked = plan_frame(queue, 10, 0)

    total = sum(item["bytes"] for item in queue if item["id"] in picked)
    assert total <= 10
    assert picked == ["a"]


def test_plan_frame_puts_expired_tasks_first():
    """缺陷 3：过期任务必须排在本帧最前面，不能按优先级被无限推后。"""
    queue = []
    enqueue(queue, task("fresh-critical", 1, 9, 1000))
    enqueue(queue, task("overdue", 1, 1, 5))

    assert plan_frame(queue, 2, 10) == ["overdue", "fresh-critical"]


def test_dequeue_unknown_id_raises_upload_error():
    """缺陷 4：未知 id 必须报错，不能静默忽略后让调用方以为成功。"""
    queue = [task("a", 1, 1, 10)]

    with pytest.raises(UploadError):
        dequeue(queue, ["missing"])
    assert ids(queue) == ["a"]


def test_expire_removes_tasks_from_queue():
    """缺陷 5：过期清理必须真正删除，只打标记会让任务下一帧又被选中。"""
    queue = []
    enqueue(queue, task("late", 1, 5, 3))
    enqueue(queue, task("ok", 1, 5, 50))

    assert expire(queue, 10) == ["late"]
    assert ids(queue) == ["ok"]


def test_estimate_frames_rounds_up():
    """缺陷 6：帧数必须向上取整，向下取整会永远剩下最后一帧任务。"""
    queue = []
    for index in range(3):
        enqueue(queue, task("t%d" % index, 3, 5, 100))

    assert estimate_frames(queue, 4) == 3


def test_reorder_repacks_queue_by_new_priority():
    """缺陷 7：改优先级必须重新稳定排序，不能还按旧顺序出队。"""
    queue = []
    enqueue(queue, task("a", 1, 1, 100))
    enqueue(queue, task("b", 1, 5, 100))
    enqueue(queue, task("c", 1, 1, 100))

    updated = reorder(queue, "c", 9)

    assert updated["priority"] == 9
    assert ids(queue) == ["c", "b", "a"]


def test_validate_reports_task_over_budget():
    """缺陷 8：单任务超预算必须出现在问题列表里，否则它永远排不上。"""
    queue = [
        task("small", 4, 5, 100),
        task("huge", 40, 9, 100),
    ]

    problems = validate(queue, 10)

    assert len(problems) == 1
    assert "huge" in problems[0]


def test_upload_batch_does_not_leak_between_queues():
    """缺陷 9：批量规划必须按队列隔离，共用列表引用会让队列互相串。"""
    first = [task("a1", 2, 5, 100), task("a2", 2, 4, 100)]
    second = [task("b1", 2, 5, 100)]

    plans = upload_batch({"a": first, "b": second}, 4, 0)

    assert plans["a"] == ["a1", "a2"]
    assert plans["b"] == ["b1"]
    assert ids(first) == ["a1", "a2"]
    assert ids(second) == ["b1"]


def test_estimate_frames_rejects_zero_budget():
    """缺陷 10：零预算必须在除法之前拦下，抛 UploadError 而不是除零。"""
    queue = [task("a", 1, 1, 10)]

    with pytest.raises(UploadError):
        estimate_frames(queue, 0)


def test_plan_frame_empty_queue_returns_empty_list():
    """组合：空队列的本帧规划返回空列表。"""
    assert plan_frame([], 100, 0) == []


def test_plan_frame_allows_task_exactly_at_budget():
    """组合：单任务字节恰好等于预算时允许上传（边界不超预算）。"""
    queue = [task("solo", 8, 3, 100)]

    assert plan_frame(queue, 8, 0) == ["solo"]


def test_plan_frame_rejects_zero_budget():
    """组合：零预算帧非法，plan_frame 抛 UploadError。"""
    queue = [task("a", 1, 1, 10)]

    with pytest.raises(UploadError):
        plan_frame(queue, 0, 0)


def test_enqueue_rejects_duplicate_id():
    """组合：重复 id 入队报 UploadError，且队列不被破坏。"""
    queue = []
    enqueue(queue, task("dup", 1, 5, 100))

    with pytest.raises(UploadError):
        enqueue(queue, task("dup", 2, 1, 100))
    assert len(queue) == 1


def test_upload_batch_success_keeps_queue_order():
    """组合：批量全部成功时不修改任何队列的内容与顺序。"""
    queue = []
    enqueue(queue, task("a", 2, 1, 100))
    enqueue(queue, task("b", 2, 5, 100))
    enqueue(queue, task("c", 2, 3, 100))
    before = ids(queue)

    plans = upload_batch({"main": queue}, 6, 0)

    assert plans["main"] == ["b", "c", "a"]
    assert ids(queue) == before

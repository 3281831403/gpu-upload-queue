"""按帧预算上传的任务队列。

任务字段
--------
队列里的每个任务都是一个 dict，恰好包含四个键：

``id``
    任务唯一标识（str）。
``bytes``
    上传该任务占用的字节数（int，>= 0）。
``priority``
    整数优先级，数值越大越优先。
``deadline``
    截止 tick（int），任务必须在该 tick 或之前发出。

tick 与容差
-----------
tick 是整数时间刻度，每上传一帧推进 1 tick，``now`` 是当前 tick。
过期判定带 1 tick 容差：``deadline < now`` 判为过期，``deadline == now``
仍算未过期（正好赶上最后一帧）。

队列形态
--------
``queue`` 就是 ``list[dict]``，函数一律就地修改它；队列始终保持
"``priority`` 降序、同优先级按入队顺序（FIFO）"的稳定有序状态。
"""

_REQUIRED_FIELDS = ("id", "bytes", "priority", "deadline")


class UploadError(Exception):
    """上传队列的领域异常：非法参数、未知 id、重复 id、校验失败等。"""


def _check_task(task):
    """校验任务字段，非法时抛 ``UploadError``。"""
    if not isinstance(task, dict):
        raise UploadError("task must be a dict")
    for field in _REQUIRED_FIELDS:
        if field not in task:
            raise UploadError("task missing field: %s" % field)
    if not isinstance(task["id"], str):
        raise UploadError("task id must be a str")
    for field in ("bytes", "priority", "deadline"):
        value = task[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise UploadError("task %s must be an int" % field)
    if task["bytes"] < 0:
        raise UploadError("task bytes must be >= 0: %s" % task["id"])


def _check_budget(budget_bytes):
    if not isinstance(budget_bytes, int) or isinstance(budget_bytes, bool):
        raise UploadError("budget_bytes must be an int")
    if budget_bytes <= 0:
        raise UploadError("budget_bytes must be > 0")


def _sort_stable(queue):
    """就地按 priority 降序重排；Python sort 稳定，同优先级保持先入先出。"""
    queue.sort(key=lambda item: -item["priority"])


def enqueue(queue, task):
    """按优先级把 ``task`` 插入 ``queue``，返回入队任务的浅拷贝。"""
    _check_task(task)
    if any(item["id"] == task["id"] for item in queue):
        raise UploadError("duplicate id: %s" % task["id"])
    queue.append(dict(task))
    _sort_stable(queue)
    return dict(task)


def plan_frame(queue, budget_bytes, now):
    """规划本帧要上传的任务 id 列表，不修改 ``queue``。"""
    _check_budget(budget_bytes)
    if not queue:
        return []

    def sort_key(entry):
        index, item = entry
        expired = item["deadline"] < now
        if expired:
            # 过期任务最前，内部按 deadline 升序，再按优先级降序、入队顺序。
            return (0, item["deadline"], -item["priority"], index)
        return (1, 0, -item["priority"], index)

    ordered = [item for _, item in sorted(enumerate(queue), key=sort_key)]

    picked = []
    remaining = budget_bytes
    for item in ordered:
        size = item["bytes"]
        if size <= remaining:
            picked.append(item["id"])
            remaining -= size
    return picked


def dequeue(queue, ids):
    """按 id 出队，返回 ``{"removed": [...], "remaining": [...]}``。"""
    wanted = list(dict.fromkeys(ids))  # 去重且保持顺序
    by_id = {item["id"]: item for item in queue}
    missing = [task_id for task_id in wanted if task_id not in by_id]
    if missing:
        raise UploadError("unknown id: %s" % missing[0])

    removed = [dict(by_id[task_id]) for task_id in wanted]
    wanted_set = set(wanted)
    queue[:] = [item for item in queue if item["id"] not in wanted_set]
    remaining = [dict(item) for item in queue]
    return {"removed": removed, "remaining": remaining}


def expire(queue, now):
    """移除并返回所有已过期任务的 id 列表。"""
    expired = [
        (index, item)
        for index, item in enumerate(queue)
        if item["deadline"] < now
    ]
    if not expired:
        return []
    expired_ids = {item["id"] for _, item in expired}
    queue[:] = [item for item in queue if item["id"] not in expired_ids]
    expired.sort(key=lambda entry: (entry[1]["deadline"], -entry[1]["priority"], entry[0]))
    return [item["id"] for _, item in expired]


def estimate_frames(queue, budget_bytes):
    """估算清空队列还需要的帧数，向上取整。"""
    _check_budget(budget_bytes)
    total = sum(item["bytes"] for item in queue)
    if total == 0:
        return 0
    return -(-total // budget_bytes)


def reorder(queue, id, priority):
    """修改任务优先级并重新稳定排序，返回更新后的任务浅拷贝。"""
    for item in queue:
        if item["id"] == id:
            item["priority"] = priority
            _sort_stable(queue)
            return dict(item)
    raise UploadError("unknown id: %s" % id)


def validate(queue, max_bytes):
    """检查队列，返回问题描述字符串列表；无问题返回 ``[]``。"""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise UploadError("max_bytes must be > 0")
    problems = []
    for item in queue:
        if item["bytes"] > max_bytes:
            problems.append(
                "task %s exceeds max_bytes: %d > %d"
                % (item["id"], item["bytes"], max_bytes)
            )
    seen = set()
    reported = set()
    for item in queue:
        task_id = item["id"]
        if task_id in seen and task_id not in reported:
            problems.append("duplicate id: %s" % task_id)
            reported.add(task_id)
        seen.add(task_id)
    for item in queue:
        if item["bytes"] < 0:
            problems.append("negative bytes: %s" % item["id"])
    return problems


def upload_batch(queues, budget_bytes, now):
    """为多个队列做批量帧规划，返回 ``{队列名: [任务 id, ...]}``。"""
    _check_budget(budget_bytes)
    # 先整体校验：任一队列有问题即抛错，所有队列保持调用前状态。
    for name, queue in queues.items():
        problems = validate(queue, budget_bytes)
        if problems:
            raise UploadError(
                "queue %s failed validation: %s" % (name, "; ".join(problems))
            )
    # plan_frame 不修改队列，各队列独立规划，互不共享引用。
    return {name: plan_frame(queue, budget_bytes, now) for name, queue in queues.items()}

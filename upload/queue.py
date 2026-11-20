"""按帧预算上传的任务队列。

初始骨架：8 个函数全部抛 ``NotImplementedError``，每个函数的契约写在
docstring 里；实现只允许使用标准库（``heapq``、``collections`` 等）。

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
仍算未过期（正好赶上最后一帧）。反过来说，实现的过期边界只要落在
``[now, now + 1]`` 这 1 tick 容差内，都视为符合契约。

队列形态
--------
``queue`` 就是 ``list[dict]``，函数一律就地修改它；队列始终保持
"``priority`` 降序、同优先级按入队顺序（FIFO）"的稳定有序状态。
"""


class UploadError(Exception):
    """上传队列的领域异常：非法参数、未知 id、重复 id、校验失败等。"""


def enqueue(queue, task):
    """按优先级把 ``task`` 插入 ``queue``，返回入队任务的浅拷贝。

    契约：
    - 就地修改 ``queue``（``list[dict]``），返回 ``dict(task)``。
    - 队列保持有序：``priority`` 降序；``priority`` 相同的任务保持入队
      先后顺序（FIFO），后入队的排在后面（稳定排序）。
    - 同一 ``id`` 已在队列中时抛 ``UploadError``，且不修改队列。
    - ``bytes`` 为负、缺少必需字段或字段类型不对时抛 ``UploadError``。
    """
    raise NotImplementedError("enqueue 尚未实现")


def plan_frame(queue, budget_bytes, now):
    """规划本帧要上传的任务 id 列表，不修改 ``queue``。

    契约：
    - 返回 ``list[str]``；空队列返回 ``[]``。
    - ``budget_bytes <= 0`` 抛 ``UploadError``（空预算帧不允许除零）。
    - 选中任务的总 ``bytes`` 严格不超过 ``budget_bytes``。
    - 返回顺序 = 优先顺序：先过期任务，过期任务内部按 ``deadline`` 升序
      （拖得最久的最先）；然后按 ``priority`` 降序；再按入队顺序（FIFO）。
    - 逐任务贪心累加：装不下就跳过该任务，继续尝试后面的任务，因此单个
      超预算任务不会阻塞同帧的小任务（它由 ``validate`` 报出）。
    - 过期判定见模块 docstring 的 1 tick 容差说明。
    """
    raise NotImplementedError("plan_frame 尚未实现")


def dequeue(queue, ids):
    """按 id 出队，返回 ``{"removed": [...], "remaining": [...]}``。

    契约：
    - 就地删除 ``ids`` 中列出的任务；``ids`` 的顺序即 ``removed`` 的顺序。
    - 任意一个 id 不在队列中时抛 ``UploadError``，且本次调用不删除任何
      任务（原子操作，调用方不会误以为全部成功）。
    - ``removed`` 是被删除任务的浅拷贝列表，``remaining`` 是出队后队列的
      浅拷贝（保持原有相对顺序）。
    - ``ids`` 里的重复项只出队一次，不重复报错。
    """
    raise NotImplementedError("dequeue 尚未实现")


def expire(queue, now):
    """移除并返回所有已过期任务的 id 列表。

    契约：
    - 就地删除过期任务；返回 ``list[str]``，按 ``deadline`` 升序，
      ``deadline`` 相同按 ``priority`` 降序，再按入队顺序。
    - "过期" = ``deadline < now``（1 tick 容差），``deadline == now``
      不算过期。
    - 没有过期任务时返回 ``[]``，队列不变。
    """
    raise NotImplementedError("expire 尚未实现")


def estimate_frames(queue, budget_bytes):
    """估算清空队列还需要的帧数，向上取整。

    契约：
    - 返回 ``ceil(sum(bytes) / budget_bytes)``；空队列返回 0。
    - 必须向上取整：例如 3 个 3 字节任务、预算 4，返回 3 而不是 2。
    - ``budget_bytes <= 0`` 抛 ``UploadError``（不得除零）。
    """
    raise NotImplementedError("estimate_frames 尚未实现")


def reorder(queue, id, priority):
    """修改任务优先级并重新稳定排序，返回更新后的任务浅拷贝。

    契约：
    - 就地更新 ``queue`` 中该任务的 ``priority``，然后按 enqueue 的同一
      规则重排：``priority`` 降序，同优先级保持当前相对顺序（稳定）。
    - 未知 ``id`` 抛 ``UploadError``，队列不变。
    - 返回值是含新 ``priority`` 的任务 dict。
    """
    raise NotImplementedError("reorder 尚未实现")


def validate(queue, max_bytes):
    """检查队列，返回问题描述字符串列表；无问题返回 ``[]``。

    契约（每个问题一条，互不合并）：
    - 单个任务 ``bytes > max_bytes``：
      ``"task <id> exceeds max_bytes: <bytes> > <max_bytes>"``
    - 重复 ``id``：``"duplicate id: <id>"``
    - 负 ``bytes``：``"negative bytes: <id>"``
    - ``max_bytes <= 0`` 抛 ``UploadError``。
    - 只读，不修改队列。
    """
    raise NotImplementedError("validate 尚未实现")


def upload_batch(queues, budget_bytes, now):
    """为多个队列做批量帧规划，返回 ``{队列名: [任务 id, ...]}``。

    契约：
    - ``queues`` 是 ``{name: list[task]}``；返回同样 key 的 dict。
    - 每个队列独立规划，结果与单独调用 ``plan_frame`` 一致；任务对象与
      列表不得跨队列共享或原地串改。
    - 先整体校验：任一队列 ``validate(queue, budget_bytes)`` 返回非空即抛
      ``UploadError``，且所有队列保持调用前的状态（整体回滚）。
    - 成功时按 ``queues`` 的插入顺序遍历，且不修改任何队列的内容与顺序。
    - ``budget_bytes <= 0`` 抛 ``UploadError``。
    """
    raise NotImplementedError("upload_batch 尚未实现")

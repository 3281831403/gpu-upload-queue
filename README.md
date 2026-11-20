# GPU 上传队列（每帧预算调度）

## 题面

资源流送改成每帧预算上传后，高优先级贴图总被拖到过期、带宽还超：同优先级任务每次出队顺序都在变；plan_frame 按字节贪心却允许超出 budget_bytes，本帧直接爆带宽；过期任务不优先，截止时间一再错过；dequeue 遇到未知 id 静默忽略，调用方以为成功；expire 只给过期任务打标记不删除，下一帧仍被选中；estimate_frames 向下取整，最后总会剩一帧任务；reorder 改了 priority 却不重排，仍按旧顺序出队；单任务 bytes 超过预算不报错，它永远排不上；upload_batch 让多个队列共用同一个列表引用，队列之间互相串；budget_bytes=0 不做校验，估算时直接除零。upload/queue.py 是核心，tests/test_queue.py 15个红。要修的是：同优先级按入队顺序稳定出队、每帧总字节不超预算、过期任务优先、未知 id 抛 UploadError、过期清理真正删除、帧数向上取整、改优先级后重新稳定排序、超预算任务写入 validate、批量按队列隔离且非法整体回滚、零预算抛 UploadError。

## 运行方式

在仓库根目录执行：

```
python -m pytest tests -q
```

初始（失败）状态预期输出恰为：

```
15 failed
```

要求 15 个测试全部因 `NotImplementedError` 变红，不得出现 collection /
import / syntax error；实现完成后应当是 `15 passed`。只依赖标准库与
pytest，离线运行、不使用随机数。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- `tests/` 是评测基线，不可修改；只能改 `upload/queue.py`（必要时可动
  `upload/__init__.py`、`README.md`）。
- 8 个函数：`enqueue`、`plan_frame`、`dequeue`、`expire`、`estimate_frames`、
  `reorder`、`validate`、`upload_batch`，契约见各自 docstring。
- 任务统一为 `{"id", "bytes", "priority", "deadline"}` 四个字段。
- tick 为整数时间刻度，过期判定带 1 tick 容差（`deadline < now` 才算过期）。
- 不使用外部依赖、不联网、不用随机数。

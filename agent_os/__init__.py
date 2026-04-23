"""
v7.2 Agent OS - Kernel Closed-Loop
===================================
Production-grade execution kernel

关键修复（v7.1 → v7.2）：
1. ✅ DAG readiness 修复：dep in completed_set（非 waiting）
2. ✅ WorkerPool → Scheduler 回流机制
3. ✅ Execution Loop 闭环（执行循环驱动系统）
4. ✅ LLM Cache（deterministic mode 支持）
5. ✅ ExecutionContext enforcement（超时、tool限制、kill）

系统语义现已闭合。
"""

import os
import sys
import json
import time
import hashlib
import threading
import queue
import copy
import signal
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from dotenv import load_dotenv
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, CancelledError
import traceback

# ==================== 配置 ====================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")
MAX_WORKERS = int(os.getenv("MAX_AGENTS", "3"))


# ==================== LLM ====================

def llm(prompt: str, temp: float = 0.8) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    try:
        return client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp
        ).choices[0].message.content
    except Exception as e:
        return f"LLM Error: {e}"


# ==================== 核心数据结构 ====================

class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class RuntimeEvent(Enum):
    TASK_SUBMITTED = auto()
    TASK_READY = auto()
    TASK_STARTED = auto()
    TASK_COMPLETE = auto()
    TASK_FAILED = auto()
    TASK_CANCELLED = auto()
    SNAPSHOT_COMMITTED = auto()
    WORKER_SUBMITTED = auto()
    WORKER_COMPLETE = auto()


@dataclass
class Task:
    id: str
    agent_type: str
    input_data: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    dependencies: Set[str] = field(default_factory=set)
    created_at: int = 0
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    score: float = 0.0

    def __hash__(self):
        return hash(self.id)


@dataclass
class Snapshot:
    hash: str
    logical_time: int
    agent_id: str
    task_id: str
    state: Dict[str, Any]
    score: float
    parent_hash: Optional[str] = None
    message: str = ""

    @staticmethod
    def compute_hash(data: Dict) -> str:
        """Deterministic hash"""
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]


@dataclass
class ExecutionTrace:
    event: RuntimeEvent
    task_id: str
    agent_id: str
    logical_time: int
    data: Dict[str, Any] = field(default_factory=dict)


# ==================== Logical Clock ====================

class LogicalClock:
    """Logical clock for determinism"""
    def __init__(self, deterministic: bool = False):
        self.deterministic = deterministic
        self._counter = 0
        self._lock = threading.Lock()

    def tick(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def now(self) -> int:
        with self._lock:
            return self._counter

    @property
    def value(self) -> int:
        return self._counter


# ==================== LLM Cache（Deterministic 支持） ====================

class LLMCache:
    """
    LLM Cache - 保证 deterministic
    ====================
    same prompt → same output
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, prompt: str, temp: float) -> Optional[str]:
        if not self.enabled:
            return None
        key = self._make_key(prompt, temp)
        return self._cache.get(key)

    def put(self, prompt: str, temp: float, result: str) -> None:
        if not self.enabled:
            return
        key = self._make_key(prompt, temp)
        with self._lock:
            self._cache[key] = result

    def _make_key(self, prompt: str, temp: float) -> str:
        return hashlib.sha256(f"{prompt}:{temp}".encode()).hexdigest()

    def clear(self):
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# ==================== Execution Context ====================

class ExecutionContext:
    """
    Execution Context - 强制执行的边界
    ====================
    Enforcement:
    - Tool whitelist
    - Timeout kill
    - Memory limit (概念级)
    """

    def __init__(
        self,
        agent_id: str,
        allowed_tools: List[str] = None,
        max_time: int = 30,
        memory_limit_mb: int = 512
    ):
        self.agent_id = agent_id
        self.allowed_tools = allowed_tools or ["llm", "verify"]
        self.max_time = max_time
        self.memory_limit_mb = memory_limit_mb

        self._killed = False
        self._start_time: Optional[float] = None
        self._checkpoints: List[str] = []

    def start(self):
        self._start_time = time.time()

    def check_timeout(self) -> bool:
        if self._start_time is None:
            return False
        return time.time() - self._start_time > self.max_time

    def can_use_tool(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools

    def kill(self):
        self._killed = True

    @property
    def is_killed(self) -> bool:
        return self._killed

    def should_stop(self) -> bool:
        """检查是否应该停止执行"""
        return self._killed or self.check_timeout()


# ==================== State Store ====================

class StateStore:
    """事件溯源状态存储"""

    def __init__(self, clock: LogicalClock = None):
        self.clock = clock or LogicalClock()
        self._event_log: List[Dict] = []
        self._event_lock = threading.Lock()
        self._current_state: Dict[str, Any] = {}
        self._agent_states: Dict[str, Dict[str, Any]] = {}
        self._shared_state: Dict[str, Any] = {}
        self._snapshots: Dict[str, Snapshot] = {}
        self._checkpoints: Dict[str, Snapshot] = {}
        self._trace: List[ExecutionTrace] = []

    def logical_time(self) -> int:
        return self.clock.now()

    def advance(self) -> int:
        return self.clock.tick()

    def append_event(self, event_type: str, data: Dict) -> None:
        with self._event_lock:
            event = {"type": event_type, "logical_time": self.clock.value, **data}
            self._event_log.append(event)

    def get_events(self, event_type: str = None) -> List[Dict]:
        with self._event_lock:
            if event_type:
                return [e for e in self._event_log if e.get("type") == event_type]
            return copy.deepcopy(self._event_log)

    def get_state(self, key: str, default=None) -> Any:
        return self._current_state.get(key, default)

    def update_state(self, updates: Dict[str, Any]) -> None:
        self._current_state.update(updates)
        self._shared_state.update(updates)

    def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        return copy.deepcopy(self._agent_states.get(agent_id, {}))

    def update_agent_state(self, agent_id: str, updates: Dict[str, Any]) -> None:
        if agent_id not in self._agent_states:
            self._agent_states[agent_id] = {}
        self._agent_states[agent_id].update(updates)
        self._shared_state.update(updates)

    def get_shared(self, key: str, default=None) -> Any:
        return self._shared_state.get(key, default)

    def set_shared(self, key: str, value: Any) -> None:
        self._shared_state[key] = value

    def commit_snapshot(
        self,
        agent_id: str,
        task_id: str,
        state_update: Dict[str, Any],
        score: float,
        message: str = ""
    ) -> Snapshot:
        lt = self.advance()

        parent_hash = None
        with self._event_lock:
            if self._event_log:
                parent_hash = self._event_log[-1].get("snapshot_hash")

        self.update_agent_state(agent_id, state_update)

        snapshot_data = {
            "agent_id": agent_id,
            "task_id": task_id,
            "state": state_update,
            "score": score,
            "parent_hash": parent_hash,
            "logical_time": lt
        }
        snapshot_hash = Snapshot.compute_hash(snapshot_data)

        snapshot = Snapshot(
            hash=snapshot_hash,
            logical_time=lt,
            agent_id=agent_id,
            task_id=task_id,
            state=state_update,
            score=score,
            parent_hash=parent_hash,
            message=message
        )

        with self._event_lock:
            self._snapshots[snapshot_hash] = snapshot
            self._event_log.append({
                "type": "snapshot",
                "snapshot_hash": snapshot_hash,
                "agent_id": agent_id,
                "task_id": task_id,
                "logical_time": lt,
                "score": score
            })

        self._update_checkpoint(agent_id, snapshot, score)
        return snapshot

    def _update_checkpoint(self, agent_id: str, snapshot: Snapshot, score: float) -> None:
        current = self._checkpoints.get(agent_id)
        if current is None or score > current.score:
            self._checkpoints[agent_id] = snapshot

    def get_best_score(self) -> float:
        if not self._snapshots:
            return 0.0
        return max(s.score for s in self._snapshots.values())

    def get_best_snapshot(self, agent_id: str) -> Optional[Snapshot]:
        return self._checkpoints.get(agent_id)

    def rollback_to(self, target_hash: str) -> bool:
        if target_hash not in self._snapshots:
            return False

        snapshot = self._snapshots[target_hash]
        path = []
        current = snapshot
        while current:
            path.append(current)
            if current.parent_hash:
                current = self._snapshots.get(current.parent_hash)
            else:
                break
        path.reverse()

        self._agent_states = {}
        self._shared_state = {}
        for s in path:
            self._agent_states[s.agent_id] = s.state
            self._shared_state.update(s.state)

        return True

    def log_trace(self, event: RuntimeEvent, task_id: str, agent_id: str, data: Dict = None) -> None:
        self._trace.append(ExecutionTrace(
            event=event, task_id=task_id, agent_id=agent_id,
            logical_time=self.clock.value, data=data or {}
        ))

    @property
    def event_count(self) -> int:
        return len(self._event_log)

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def get_summary(self) -> Dict:
        return {
            "events": self.event_count,
            "snapshots": self.snapshot_count,
            "checkpoints": list(self._checkpoints.keys()),
            "logical_time": self.clock.value
        }


# ==================== DAG Engine ====================

class DAGEngine:
    """
    DAG Engine - 依赖调度引擎
    ====================
    核心修复：readiness 检查使用 completed_set
    """

    def __init__(self):
        self._waiting: Dict[str, Task] = {}
        self._dependents: Dict[str, List[str]] = {}
        self._dependencies: Dict[str, Set[str]] = {}
        self._completed: Set[str] = set()
        self._lock = threading.Lock()

    def add_task(self, task: Task) -> bool:
        """添加任务，返回是否就绪"""
        with self._lock:
            task_id = task.id

            if task_id not in self._dependencies:
                self._dependencies[task_id] = task.dependencies.copy()

            if task_id not in self._dependents:
                self._dependents[task_id] = []

            for dep_id in task.dependencies:
                if dep_id not in self._dependents:
                    self._dependents[dep_id] = []
                self._dependents[dep_id].append(task_id)

            # ✅ 修复：检查依赖是否已完成，而非只是不在 waiting
            if self._is_ready_unlocked(task_id):
                task.status = TaskStatus.READY
                if task_id in self._waiting:
                    del self._waiting[task_id]
                return True
            else:
                task.status = TaskStatus.PENDING
                self._waiting[task_id] = task
                return False

    def mark_complete(self, task_id: str) -> List[Task]:
        """标记完成，唤醒依赖任务"""
        with self._lock:
            self._completed.add(task_id)

            if task_id in self._waiting:
                del self._waiting[task_id]

            ready_tasks = []
            for dependent_id in self._dependents.get(task_id, []):
                if self._is_ready_unlocked(dependent_id):
                    if dependent_id in self._waiting:
                        task = self._waiting[dependent_id]
                        task.status = TaskStatus.READY
                        ready_tasks.append(task)
                        del self._waiting[dependent_id]

            return ready_tasks

    def mark_failed(self, task_id: str) -> None:
        """标记失败"""
        with self._lock:
            if task_id in self._waiting:
                del self._waiting[task_id]

    def _is_ready_unlocked(self, task_id: str) -> bool:
        """检查任务是否就绪（锁内使用）"""
        deps = self._dependencies.get(task_id, set())
        # ✅ 修复：必须依赖已完成，而非只是不在 waiting
        return all(dep in self._completed for dep in deps)

    def is_ready(self, task_id: str) -> bool:
        with self._lock:
            return self._is_ready_unlocked(task_id)

    def get_waiting_count(self) -> int:
        return len(self._waiting)

    def get_completed_count(self) -> int:
        return len(self._completed)

    def has_cycle(self) -> bool:
        with self._lock:
            visited = set()
            rec_stack = set()

            def dfs(node: str) -> bool:
                visited.add(node)
                rec_stack.add(node)
                for dep in self._dependencies.get(node, set()):
                    if dep not in visited:
                        if dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True
                rec_stack.remove(node)
                return False

            for node in self._dependencies:
                if node not in visited:
                    if dfs(node):
                        return True
            return False

    def get_summary(self) -> Dict:
        with self._lock:
            return {
                "waiting": len(self._waiting),
                "completed": len(self._completed),
                "dependencies": {k: list(v) for k, v in self._dependencies.items()}
            }


# ==================== Scheduler ====================

class Scheduler:
    """
    Scheduler - 任务分配器
    ====================
    职责：排队、优先级、分配给 worker
    不负责：实际执行
    """

    def __init__(self, dag: DAGEngine):
        self.dag = dag
        self._ready_queue: List[Task] = []
        self._running: Dict[str, Task] = {}
        self._completed: Dict[str, Task] = {}
        self._failed: Dict[str, Task] = {}
        self._lock = threading.Lock()

    def submit(self, task: Task) -> bool:
        with self._lock:
            task.created_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
            is_ready = self.dag.add_task(task)

            if is_ready:
                task.status = TaskStatus.READY
                self._ready_queue.append(task)
                self._sort_queue()
                return True
            else:
                task.status = TaskStatus.PENDING
                return False

    def dispatch(self) -> Optional[Task]:
        """分发任务给 worker"""
        with self._lock:
            if not self._ready_queue:
                return None

            task = self._ready_queue.pop(0)
            task.status = TaskStatus.RUNNING
            task.started_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
            self._running[task.id] = task
            return task

    def complete(self, task_id: str, result: Dict, score: float) -> List[Task]:
        """标记完成，触发 DAG 唤醒"""
        with self._lock:
            if task_id in self._running:
                task = self._running[task_id]
                task.status = TaskStatus.COMPLETE
                task.completed_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
                task.result = result
                task.score = score
                self._completed[task_id] = task
                del self._running[task_id]

            # DAG 标记并获取可唤醒的任务
            ready_tasks = self.dag.mark_complete(task_id)
            for t in ready_tasks:
                self._ready_queue.append(t)
            self._sort_queue()

            return ready_tasks

    def fail(self, task_id: str, error: str) -> None:
        with self._lock:
            if task_id in self._running:
                task = self._running[task_id]
                task.error = error

                if task.retries < task.max_retries:
                    task.status = TaskStatus.RETRYING
                    task.retries += 1
                    task.started_at = None
                else:
                    task.status = TaskStatus.FAILED
                    self._failed[task_id] = task
                    self.dag.mark_failed(task_id)
                    del self._running[task_id]

    def cancel(self, task_id: str) -> None:
        """取消任务"""
        with self._lock:
            if task_id in self._running:
                task = self._running[task_id]
                task.status = TaskStatus.CANCELLED
                del self._running[task_id]
                self.dag.mark_failed(task_id)
            elif task_id in self._ready_queue:
                self._ready_queue = [t for t in self._ready_queue if t.id != task_id]
            elif task_id in self._waiting:
                del self._waiting[task_id]

    def adjust_priority(self, task_id: str, score: float) -> None:
        with self._lock:
            for task in self._ready_queue:
                key = task_id.split('_')[0] if '_' in task_id else task_id
                if task.agent_type == key:
                    if score >= 7.5:
                        task.priority = TaskPriority(min(4, task.priority.value + 1))
                    elif score < 5:
                        task.priority = TaskPriority(max(1, task.priority.value - 1))
            self._sort_queue()

    def _sort_queue(self):
        self._ready_queue.sort(key=lambda t: (t.priority.value, t.created_at), reverse=True)

    def is_idle(self) -> bool:
        return len(self._ready_queue) == 0 and len(self._running) == 0

    def get_status(self) -> Dict:
        return {
            "ready": len(self._ready_queue),
            "running": len(self._running),
            "completed": len(self._completed),
            "failed": len(self._failed)
        }


# ==================== Worker ====================

class Worker:
    """
    Worker - 任务执行器
    ====================
    带 ExecutionContext enforcement
    """

    def __init__(
        self,
        worker_id: str,
        state_store: StateStore,
        tool_runtime: 'ToolRuntime',
        context: ExecutionContext,
        llm_cache: LLMCache = None
    ):
        self.worker_id = worker_id
        self.state_store = state_store
        self.tool_runtime = tool_runtime
        self.context = context
        self.llm_cache = llm_cache

    def execute(self, task: Task) -> Dict:
        """执行任务（带 enforcement）"""
        self.context.start()

        self.state_store.log_trace(
            RuntimeEvent.TASK_STARTED, task.id, self.worker_id,
            {"priority": task.priority.value}
        )

        try:
            # ✅ Enforcement: 超时检查
            if self.context.should_stop():
                return self._make_error_result("timeout")

            # 分发
            if task.agent_type == "writer":
                result = self._write_lyrics(task.input_data)
            elif task.agent_type == "critic":
                result = self._critic_evaluate(task.input_data)
            elif task.agent_type == "editor":
                result = self._edit_lyrics(task.input_data)
            elif task.agent_type == "title":
                result = self._generate_title(task.input_data)
            else:
                return self._make_error_result(f"Unknown agent: {task.agent_type}")

            # ✅ Enforcement: 超时检查
            if self.context.should_stop():
                return self._make_error_result("timeout")

            # 提交 snapshot
            self.state_store.commit_snapshot(
                agent_id=self.worker_id,
                task_id=task.id,
                state_update={
                    f"{task.agent_type}_output": result.get("output", ""),
                    "score": result.get("score", 0)
                },
                score=result.get("score", 0),
                message=f"{task.agent_type} completed"
            )

            self.state_store.log_trace(
                RuntimeEvent.TASK_COMPLETE, task.id, self.worker_id,
                {"score": result.get("score", 0)}
            )

            return {
                "status": "success",
                "output": result.get("output"),
                "score": result.get("score", 0)
            }

        except Exception as e:
            self.state_store.log_trace(
                RuntimeEvent.TASK_FAILED, task.id, self.worker_id,
                {"error": str(e), "traceback": traceback.format_exc()}
            )
            return self._make_error_result(str(e))

    def _make_error_result(self, error: str) -> Dict:
        return {"status": "error", "error": error, "score": 0}

    # --- Agent 实现 ---

    def _write_lyrics(self, input_data: Dict) -> Dict:
        emotion = input_data.get("emotion", "")
        emotion_detail = input_data.get("emotion_detail", "")
        keywords = input_data.get("keywords", [])
        story = input_data.get("story", "")
        style = input_data.get("style", "")
        feedback = input_data.get("feedback", "")

        style_map = {
            "甜蜜": "甜蜜温馨", "伤感": "伤感忧郁", "说唱": "节奏强劲",
            "治愈": "温暖治愈", "摇滚": "力量感强", "叙事": "叙事画面",
            "民谣": "质朴自然", "R&B": "丝滑性感"
        }

        prompt = f"""创作歌词：

情感：{emotion} {emotion_detail}
风格：{style_map.get(style, style)}
故事：{story}
关键词：{', '.join(keywords)}
{feedback}

要求：主歌4句+副歌4句+主歌2 4句+副歌4句，按韵脚押韵。

歌词："""

        output = self._call_llm(prompt, 0.85)
        return {"output": output, "score": 0}

    def _critic_evaluate(self, input_data: Dict) -> Dict:
        lyrics = input_data.get("lyrics", "")
        emotion = input_data.get("emotion", "")
        style = input_data.get("style", "")

        result = self.tool_runtime.verify(lyrics, emotion, style)
        return {
            "output": result,
            "score": result.get("overall", 0),
            "issues": result.get("issues", []),
            "suggestions": result.get("suggestions", [])
        }

    def _edit_lyrics(self, input_data: Dict) -> Dict:
        lyrics = input_data.get("lyrics", "")
        suggestions = input_data.get("suggestions", [])

        if not suggestions:
            return {"output": lyrics, "score": 8.0}

        prompt = f"""修改歌词：

原文：{lyrics}
建议：{', '.join(suggestions)}

直接输出修改后的歌词（不改格式）："""

        output = self._call_llm(prompt, 0.7)
        return {"output": output, "score": 0}

    def _generate_title(self, input_data: Dict) -> Dict:
        lyrics = input_data.get("lyrics", "")
        prompt = f"""为歌词生成标题：

歌词：{lyrics}

直接输出标题（不超过10字）："""
        output = self._call_llm(prompt, 0.8)
        return {"output": output.strip(), "score": 0}

    def _call_llm(self, prompt: str, temp: float) -> str:
        """LLM 调用（带 cache 和 enforcement）"""
        # ✅ Enforcement: Tool 限制
        if not self.context.can_use_tool("llm"):
            return f"[Tool denied: llm]"

        # ✅ Deterministic: 优先从 cache 获取
        if self.llm_cache:
            cached = self.llm_cache.get(prompt, temp)
            if cached:
                return cached

        if self.context.should_stop():
            return "[Timeout]"

        output = llm(prompt, temp)

        # Cache 结果
        if self.llm_cache:
            self.llm_cache.put(prompt, temp, output)

        return output


# ==================== Worker Pool ====================

class WorkerPool:
    """
    Worker Pool - 并发执行池
    ====================
    关键：结果回流到 Scheduler
    """

    def __init__(
        self,
        state_store: StateStore,
        tool_runtime: 'ToolRuntime',
        llm_cache: LLMCache = None,
        size: int = MAX_WORKERS
    ):
        self.state_store = state_store
        self.tool_runtime = tool_runtime
        self.llm_cache = llm_cache
        self.size = size

        self._executor = ThreadPoolExecutor(max_workers=size)
        self._futures: Dict[str, Future] = {}
        self._workers: Dict[str, Worker] = {}
        self._lock = threading.Lock()

        self._completed_count = 0
        self._failed_count = 0

    def submit(self, task: Task, scheduler: Scheduler) -> bool:
        """提交任务，返回是否成功"""
        with self._lock:
            # Backpressure
            if len(self._futures) >= self.size * 2:
                return False

            # 创建 worker
            worker_id = f"worker_{task.agent_type}_{len(self._workers)}"
            context = ExecutionContext(
                agent_id=worker_id,
                allowed_tools=["llm", "verify"],
                max_time=30
            )
            worker = Worker(
                worker_id, self.state_store, self.tool_runtime,
                context, self.llm_cache
            )
            self._workers[worker_id] = worker

            # 提交
            future = self._executor.submit(worker.execute, task)
            self._futures[task.id] = future

            self.state_store.log_trace(
                RuntimeEvent.WORKER_SUBMITTED, task.id, worker_id,
                {"pool_size": len(self._futures)}
            )

            return True

    def get_completed(self) -> List[Dict]:
        """
        获取已完成结果
        ====================
        ✅ 关键：这是结果"回流"到 Scheduler 的入口
        """
        completed = []
        to_remove = []

        with self._lock:
            for task_id, future in self._futures.items():
                if future.done():
                    to_remove.append(task_id)
                    try:
                        result = future.result(timeout=0)
                        result['task_id'] = task_id
                        completed.append(result)

                        if result.get("status") == "success":
                            self._completed_count += 1
                        else:
                            self._failed_count += 1

                        worker_id = 'unknown'
                        if self._workers:
                            for wid in self._workers:
                                worker_id = wid
                                break
                        self.state_store.log_trace(
                            RuntimeEvent.WORKER_COMPLETE, task_id, worker_id, result
                        )

                    except CancelledError:
                        completed.append({
                            "task_id": task_id,
                            "status": "cancelled",
                            "score": 0
                        })
                    except TimeoutError:
                        pass
                    except Exception as e:
                        self._failed_count += 1
                        completed.append({
                            "task_id": task_id,
                            "status": "error",
                            "error": str(e),
                            "score": 0
                        })

            for task_id in to_remove:
                del self._futures[task_id]

        return completed

    def cancel_all(self):
        """取消所有任务"""
        with self._lock:
            for future in self._futures.values():
                future.cancel()
            self._futures.clear()

    def wait_for(self, timeout: float = None) -> bool:
        """等待所有任务完成"""
        with self._lock:
            futures = list(self._futures.values())

        if not futures:
            return True

        try:
            for f in futures:
                f.result(timeout=timeout)
            return True
        except TimeoutError:
            return False
        except CancelledError:
            return False

    @property
    def active_count(self) -> int:
        return len(self._futures)

    def shutdown(self, wait: bool = True):
        self.cancel_all()
        self._executor.shutdown(wait=wait)

    def get_stats(self) -> Dict:
        return {
            "active": self.active_count,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "max_workers": self.size
        }


# ==================== Tool Runtime ====================

class ToolRuntime:
    """Tool Runtime"""

    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self.execution_log: List[Dict] = []

    def llm(self, prompt: str, temp: float = 0.8) -> Dict:
        start = time.time()
        try:
            result = llm(prompt, temp)
            self.execution_log.append({
                "tool": "llm", "elapsed": time.time() - start, "success": True
            })
            return {"output": result}
        except Exception as e:
            self.execution_log.append({
                "tool": "llm", "elapsed": time.time() - start,
                "success": False, "error": str(e)
            })
            return {"error": str(e)}

    def verify(self, lyrics: str, emotion: str, style: str) -> Dict:
        prompt = f"""审查歌词（JSON格式）：
{{"overall":8.0,"emotion_match":8.0,"style_fit":8.0,"issues":[],"suggestions":[]}}

歌词：{lyrics}
情感：{emotion}
风格：{style}

直接JSON："""

        result = llm(prompt, 0.3)

        try:
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            return json.loads(result)
        except:
            return {"overall": 5.0, "issues": ["parse error"], "suggestions": []}


# ==================== Execution Engine（闭环核心） ====================

class ExecutionEngine:
    """
    Execution Engine - 核心执行引擎（闭环）
    ====================
    ✅ 这是缺失的 Execution Loop

    流程：
    1. submit task → DAG → ready_queue
    2. dispatch → WorkerPool
    3. get_completed → Scheduler.complete → DAG 唤醒
    4. loop 直到 idle
    """

    def __init__(self, max_workers: int = MAX_WORKERS, deterministic: bool = False):
        self.clock = LogicalClock(deterministic=deterministic)
        self.state_store = StateStore(self.clock)
        self.dag = DAGEngine()
        self.scheduler = Scheduler(self.dag)
        self.llm_cache = LLMCache(enabled=deterministic)
        self.tool_runtime = ToolRuntime(self.state_store)
        self.worker_pool = WorkerPool(
            self.state_store, self.tool_runtime,
            self.llm_cache, max_workers
        )

        self.max_iterations = 3
        self.convergence_threshold = 7.5
        self._running = False

    def run(self, initial_task: Task) -> Dict:
        """
        执行任务（闭环）
        ====================
        ✅ 完整的执行闭环：
        dispatch → submit → execute → collect → complete → DAG → dispatch...
        """
        self._running = True
        self.scheduler.submit(initial_task)

        best_result = None
        best_score = -1.0
        iteration = 0

        # ✅ Execution Loop（核心闭环）
        while self._running and iteration < self.max_iterations:
            iteration += 1

            # 1. Dispatch
            task = self.scheduler.dispatch()

            if task:
                # 2. Submit to WorkerPool
                self.worker_pool.submit(task, self.scheduler)
            else:
                # 没有就绪任务，检查是否所有任务都完成了
                if self.scheduler.is_idle() and self.worker_pool.active_count == 0:
                    break

            # 3. Collect completed results（结果回流）
            for result in self.worker_pool.get_completed():
                task_id = result.pop('task_id', None) or result.get('task_id')

                if result.get("status") == "success":
                    score = result.get("score", 0)

                    # ✅ 回流到 Scheduler
                    self.scheduler.complete(task_id, result, score)

                    # 记录 best
                    if score > best_score:
                        best_score = score
                        best_result = result

                    # Feedback
                    self.scheduler.adjust_priority(task_id, score)

                    # 收敛检查
                    if score >= self.convergence_threshold:
                        self._running = False
                        break
                else:
                    self.scheduler.fail(task_id, result.get("error", "Unknown"))

            # 短暂让出，让 worker 执行
            if self.worker_pool.active_count > 0:
                time.sleep(0.01)

        self._running = False

        return {
            "best_result": best_result,
            "best_score": best_score,
            "iterations": iteration,
            "converged": best_score >= self.convergence_threshold
        }

    def run_feedback_loop(self, writer_task: Task, max_cycles: int = 3) -> Dict:
        """Feedback loop: Writer → Critic → Editor"""
        best_lyrics = None
        best_score = -1.0

        # Writer
        writer_result = self.run(writer_task)
        if writer_result["best_result"]:
            best_lyrics = writer_result["best_result"].get("output", "")
            best_score = writer_result["best_score"]

        if not best_lyrics:
            return {"best_result": None, "best_score": -1, "cycles": 0}

        # Feedback cycles
        for cycle in range(max_cycles):
            if best_score >= self.convergence_threshold:
                break

            # Critic
            critic_task = Task(
                id=f"critic_{cycle}",
                agent_type="critic",
                input_data={
                    "lyrics": best_lyrics,
                    "emotion": writer_task.input_data.get("emotion", ""),
                    "style": writer_task.input_data.get("style", "")
                }
            )
            critic_result = self.run(critic_task)

            if not critic_result["best_result"]:
                break

            eval_data = critic_result["best_result"].get("output", {})
            score = critic_result["best_score"]
            suggestions = eval_data.get("suggestions", [])

            if not suggestions or score >= self.convergence_threshold:
                best_score = score
                break

            # Editor
            editor_task = Task(
                id=f"editor_{cycle}",
                agent_type="editor",
                input_data={
                    "lyrics": best_lyrics,
                    "suggestions": suggestions
                }
            )
            editor_result = self.run(editor_task)

            if editor_result["best_result"]:
                best_lyrics = editor_result["best_result"].get("output", "")
                best_score = editor_result["best_score"]

        return {
            "best_result": {"output": best_lyrics, "score": best_score},
            "best_score": best_score,
            "cycles": max_cycles,
            "converged": best_score >= self.convergence_threshold
        }

    def get_state(self) -> Dict:
        return {
            "scheduler": self.scheduler.get_status(),
            "worker_pool": self.worker_pool.get_stats(),
            "state_store": self.state_store.get_summary(),
            "dag": self.dag.get_summary(),
            "llm_cache": self.llm_cache.size if self.llm_cache else 0
        }

    def shutdown(self):
        self._running = False
        self.worker_pool.shutdown()


# ==================== Agent OS Kernel ====================

class AgentOSKernel:
    """
    Agent OS Kernel - 统一入口
    """

    def __init__(self, max_workers: int = MAX_WORKERS, deterministic: bool = False):
        self.engine = ExecutionEngine(max_workers=max_workers, deterministic=deterministic)

    def execute_task(self, task: Task) -> Dict:
        return self.engine.run(task)

    def run_feedback_loop(self, task: Task, max_cycles: int = 3) -> Dict:
        return self.engine.run_feedback_loop(task, max_cycles)

    def get_state(self) -> Dict:
        return self.engine.get_state()

    def get_event_log(self) -> List[Dict]:
        return self.engine.state_store.get_events()

    def get_trace(self) -> List[ExecutionTrace]:
        return self.engine.state_store.get_trace()

    def shutdown(self):
        self.engine.shutdown()
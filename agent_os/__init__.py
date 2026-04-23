"""
v7.5 Agent OS - Execution Gate + System Health
============================================
核心升级：统一执行门控层

v7.4 → v7.5：
1. Execution Gate - 统一的任务入口和准入控制
2. System Health Score - 系统健康度量化
3. Global Feedback Loop - 执行结果闭环反馈

从 "分散控制点" → "统一执行门控"

系统架构：
                ┌─────────────────────┐
                │   Agent Layer       │
                └──────────┬──────────┘
                           │
                ┌──────────▼──────────┐
                │   Execution Gate    │  ← v7.5 统一入口
                │  (control plane)    │
                └──────────┬──────────┘
                           │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼───────┐
│   Admission   │  │  Backpressure │  │    Cost       │
│   Control     │  │   Control     │  │    Model      │
└───────────────┘  └───────────────┘  └───────────────┘
                           │
                ┌──────────▼──────────┐
                │   Scheduler v7.4    │
                │  (decision layer)   │
                └──────────┬──────────┘
                           │
                ┌──────────▼──────────┐
                │    WorkerPool        │
                │  (execution layer)   │
                └─────────────────────┘
"""

import os
import sys
import json
import time
import hashlib
import threading
import queue
import copy
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

# 调度配置
DEFAULT_LOAD_THRESHOLD = 0.8
DEFAULT_QUEUE_HIGH_WATER = 10


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
    DELAYED = "delayed"
    REJECTED = "rejected"  # v7.5 新增


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class GateDecision(Enum):
    """Execution Gate 决策"""
    ACCEPT = "accept"      # 接受执行
    DELAY = "delay"       # 延迟执行
    REJECT = "reject"      # 拒绝执行


class RuntimeEvent(Enum):
    TASK_SUBMITTED = auto()
    TASK_READY = auto()
    TASK_STARTED = auto()
    TASK_COMPLETE = auto()
    TASK_FAILED = auto()
    TASK_DELAYED = auto()
    TASK_REJECTED = auto()    # v7.5
    WORKER_SUBMITTED = auto()
    WORKER_COMPLETE = auto()
    SCHEDULING_DECISION = auto()
    ADMISSION_REJECTED = auto()
    BACKPRESSURE_TRIGGERED = auto()
    GATE_DECISION = auto()    # v7.5


class WorkerType(Enum):
    LLM = "llm"
    IO = "io"
    GENERAL = "general"


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

    # 调度相关
    estimated_cost: float = 1.0
    depth: int = 0
    worker_type: WorkerType = WorkerType.GENERAL

    # 实际成本追踪
    actual_cost: float = 0.0
    execution_start: Optional[float] = None

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
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]


@dataclass
class GateResult:
    """Execution Gate 决策结果"""
    decision: GateDecision
    task_id: str
    reason: str
    health_score: float  # 决策时的健康度
    queue_position: Optional[int] = None
    delay_seconds: float = 0.0


@dataclass
class SchedulingDecision:
    timestamp: float
    task_id: str
    decision: str
    reason: str
    worker_id: Optional[str] = None
    priority: int = 0
    estimated_cost: float = 0
    depth: int = 0
    admitted: bool = True
    health_score: float = 1.0  # v7.5


@dataclass
class ExecutionTrace:
    event: RuntimeEvent
    task_id: str
    agent_id: str
    logical_time: int
    data: Dict[str, Any] = field(default_factory=dict)


# ==================== Logical Clock ====================

class LogicalClock:
    def __init__(self):
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


# ==================== LLM Cache ====================

class LLMCache:
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

    @property
    def size(self) -> int:
        return len(self._cache)


# ==================== Execution Context ====================

class ExecutionContext:
    def __init__(self, agent_id: str, allowed_tools: List[str] = None, max_time: int = 30):
        self.agent_id = agent_id
        self.allowed_tools = allowed_tools or ["llm", "verify"]
        self.max_time = max_time
        self._killed = False
        self._start_time: Optional[float] = None

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

    @property
    def elapsed_time(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def should_stop(self) -> bool:
        return self._killed or self.check_timeout()


# ==================== State Store ====================

class StateStore:
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
            "agent_id": agent_id, "task_id": task_id, "state": state_update,
            "score": score, "parent_hash": parent_hash, "logical_time": lt
        }
        snapshot_hash = Snapshot.compute_hash(snapshot_data)
        snapshot = Snapshot(
            hash=snapshot_hash, logical_time=lt, agent_id=agent_id,
            task_id=task_id, state=state_update, score=score,
            parent_hash=parent_hash, message=message
        )
        with self._event_lock:
            self._snapshots[snapshot_hash] = snapshot
            self._event_log.append({
                "type": "snapshot", "snapshot_hash": snapshot_hash,
                "agent_id": agent_id, "task_id": task_id,
                "logical_time": lt, "score": score
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


# ==================== Adaptive Cost Tracker ====================

class AdaptiveCostTracker:
    """
    Adaptive Cost Tracker - 自适应成本估计
    """
    def __init__(self):
        self._cost_history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._default_costs = {
            "writer": 3.0,
            "critic": 2.0,
            "editor": 2.5,
            "title": 1.0,
        }
        self._ema_alpha = 0.3

    def get_estimated_cost(self, agent_type: str) -> float:
        with self._lock:
            if agent_type in self._cost_history and self._cost_history[agent_type]:
                history = self._cost_history[agent_type]
                ema = history[0]
                for cost in history[1:]:
                    ema = self._ema_alpha * cost + (1 - self._ema_alpha) * ema
                return max(ema, 0.1)
            return self._default_costs.get(agent_type, 1.0)

    def record_actual_cost(self, agent_type: str, actual_cost: float, task_success: bool):
        if not task_success or actual_cost <= 0:
            return
        with self._lock:
            if agent_type not in self._cost_history:
                self._cost_history[agent_type] = []
            self._cost_history[agent_type].append(actual_cost)
            if len(self._cost_history[agent_type]) > 50:
                self._cost_history[agent_type] = self._cost_history[agent_type][-50:]

    def get_cost_error(self) -> float:
        """计算成本估计误差（用于健康度）"""
        with self._lock:
            total_error = 0.0
            count = 0
            for agent_type, history in self._cost_history.items():
                if history:
                    default = self._default_costs.get(agent_type, 1.0)
                    avg = sum(history) / len(history)
                    error = abs(avg - default) / default
                    total_error += error
                    count += 1
            return total_error / max(count, 1)

    def get_learning_stats(self) -> Dict:
        with self._lock:
            stats = {}
            for agent_type, history in self._cost_history.items():
                if history:
                    stats[agent_type] = {
                        "count": len(history),
                        "avg": sum(history) / len(history),
                        "min": min(history),
                        "max": max(history),
                        "latest": history[-1]
                    }
            return stats


# ==================== DAG Engine ====================

class DAGEngine:
    def __init__(self):
        self._waiting: Dict[str, Task] = {}
        self._dependents: Dict[str, List[str]] = {}
        self._dependencies: Dict[str, Set[str]] = {}
        self._completed: Set[str] = set()
        self._task_depths: Dict[str, int] = {}
        self._lock = threading.Lock()

    def add_task(self, task: Task) -> bool:
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

            task.depth = self._calculate_depth_unlocked(task_id)

            if self._is_ready_unlocked(task_id):
                task.status = TaskStatus.READY
                if task_id in self._waiting:
                    del self._waiting[task_id]
                return True
            else:
                task.status = TaskStatus.PENDING
                self._waiting[task_id] = task
                return False

    def _calculate_depth_unlocked(self, task_id: str) -> int:
        if task_id in self._task_depths:
            return self._task_depths[task_id]
        deps = self._dependencies.get(task_id, set())
        if not deps:
            depth = 0
        else:
            max_dep_depth = 0
            for dep_id in deps:
                if dep_id in self._completed:
                    dep_depth = self._task_depths.get(dep_id, 0)
                elif dep_id in self._waiting:
                    dep_depth = self._calculate_depth_unlocked(dep_id)
                else:
                    dep_depth = 0
                max_dep_depth = max(max_dep_depth, dep_depth)
            depth = max_dep_depth + 1
        self._task_depths[task_id] = depth
        return depth

    def mark_complete(self, task_id: str) -> List[Task]:
        with self._lock:
            self._completed.add(task_id)
            if task_id in self._waiting:
                del self._waiting[task_id]
            ready_tasks = []
            for dependent_id in self._dependents.get(task_id, []):
                if dependent_id in self._waiting:
                    new_depth = self._calculate_depth_unlocked(dependent_id)
                    self._waiting[dependent_id].depth = new_depth
                if self._is_ready_unlocked(dependent_id):
                    if dependent_id in self._waiting:
                        task = self._waiting[dependent_id]
                        task.status = TaskStatus.READY
                        ready_tasks.append(task)
                        del self._waiting[dependent_id]
            return ready_tasks

    def mark_failed(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._waiting:
                del self._waiting[task_id]

    def _is_ready_unlocked(self, task_id: str) -> bool:
        deps = self._dependencies.get(task_id, set())
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
                "depths": dict(self._task_depths)
            }


# ==================== Execution Gate（v7.5 核心） ====================

class ExecutionGate:
    """
    Execution Gate - 统一执行门控
    ====================
    v7.5 核心组件：所有任务进入系统的统一入口

    职责：
    1. System Health Score - 计算系统健康度
    2. Unified Admission - 统一的准入控制
    3. Cost-aware Routing - 成本感知路由
    4. Global Feedback - 收集反馈更新模型
    """

    def __init__(
        self,
        scheduler: 'Scheduler',
        worker_pool: 'WorkerPool',
        cost_tracker: AdaptiveCostTracker,
        state_store: StateStore
    ):
        self.scheduler = scheduler
        self.worker_pool = worker_pool
        self.cost_tracker = cost_tracker
        self.state_store = state_store

        # 配置
        self.load_threshold = DEFAULT_LOAD_THRESHOLD
        self.queue_high_water = DEFAULT_QUEUE_HIGH_WATER
        self.health_weight_load = 0.4
        self.health_weight_queue = 0.3
        self.health_weight_cost_error = 0.2
        self.health_weight_rejection = 0.1

        # 统计
        self._total_submissions = 0
        self._total_rejections = 0
        self._decision_history: List[GateResult] = []

        self._lock = threading.Lock()

    def get_system_health(self) -> float:
        """
        计算系统健康度（0.0 ~ 1.0）
        ====================
        health = f(
            worker_load,      # 越低越好
            queue_size,       # 越小越好
            cost_error,       # 成本估计误差，越小越好
            rejection_rate    # 拒绝率，越低越好
        )
        """
        with self._lock:
            # 1. Worker 负载（越低越好）
            system_load = self.worker_pool.get_system_load()
            load_score = 1.0 - system_load  # 0.0 满载 → 1.0 空闲

            # 2. 队列大小（越小越好）
            queue_size = self.scheduler.get_status()["ready"]
            queue_score = max(0.0, 1.0 - queue_size / max(self.queue_high_water, 1))

            # 3. 成本估计误差（越小越好）
            cost_error = self.cost_tracker.get_cost_error()
            cost_score = max(0.0, 1.0 - cost_error)

            # 4. 拒绝率（越低越好）
            rejection_rate = (
                self._total_rejections / max(self._total_submissions, 1)
            )
            rejection_score = 1.0 - rejection_rate

            # 加权健康度
            health = (
                self.health_weight_load * load_score +
                self.health_weight_queue * queue_score +
                self.health_weight_cost_error * cost_score +
                self.health_weight_rejection * rejection_score
            )

            return max(0.0, min(1.0, health))

    def evaluate(self, task: Task) -> GateResult:
        """
        评估任务是否可接受（统一门控）
        ====================
        v7.5 核心：单一入口，统一决策
        """
        with self._lock:
            self._total_submissions += 1
            health = self.get_system_health()

            # 决策因素
            system_load = self.worker_pool.get_system_load()
            queue_size = self.scheduler.get_status()["ready"]
            queue_total = queue_size + len(self.scheduler._delayed_queue)

            # 决策逻辑
            if system_load >= 0.95:
                # 极端过载 → 拒绝
                self._total_rejections += 1
                decision = GateDecision.REJECT
                reason = f"system overload: load={system_load:.2f}"
                self._log_decision(task.id, decision, reason, health)

            elif queue_total >= self.queue_high_water:
                # 队列过满 → 根据优先级决定
                if task.priority == TaskPriority.CRITICAL:
                    decision = GateDecision.ACCEPT
                    reason = f"critical task bypasses queue limit"
                else:
                    decision = GateDecision.DELAY
                    reason = f"queue full: {queue_total} >= {self.queue_high_water}"
                    self._log_decision(task.id, decision, reason, health)
            else:
                # 正常 → 接受
                decision = GateDecision.ACCEPT
                reason = f"healthy: load={system_load:.2f}, queue={queue_total}"
                self._log_decision(task.id, decision, reason, health)

            return GateResult(
                decision=decision,
                task_id=task.id,
                reason=reason,
                health_score=health
            )

    def route_task(self, task: Task) -> Optional[str]:
        """
        成本感知路由
        ====================
        v7.5：cheap task → low load worker
              expensive task → idle worker
        """
        workers = self.worker_pool.get_worker_stats()

        if not workers:
            return None

        estimated_cost = task.estimated_cost

        # 根据成本选择
        if estimated_cost < 2.0:
            # 便宜任务 → 选择负载最低的
            best = min(workers, key=lambda w: w["load"])
        else:
            # 昂贵任务 → 选择最空闲的（负载<0.3）
            idle_workers = [w for w in workers if w["load"] < 0.3]
            if idle_workers:
                best = idle_workers[0]
            else:
                best = min(workers, key=lambda w: w["load"])

        return best["worker_id"] if best else None

    def on_task_complete(self, task_id: str, score: float, actual_cost: float, success: bool):
        """任务完成回调：更新成本模型"""
        # 成本追踪已由 Scheduler 处理
        pass

    def _log_decision(self, task_id: str, decision: GateDecision, reason: str, health: float):
        self.state_store.log_trace(
            RuntimeEvent.GATE_DECISION,
            task_id,
            "execution_gate",
            {
                "decision": decision.value,
                "reason": reason,
                "health": health
            }
        )

        self._decision_history.append(GateResult(
            decision=decision,
            task_id=task_id,
            reason=reason,
            health_score=health
        ))

        # 保留最近 100 条
        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]

    def get_health_breakdown(self) -> Dict:
        """获取健康度明细"""
        system_load = self.worker_pool.get_system_load()
        queue_size = self.scheduler.get_status()["ready"]
        cost_error = self.cost_tracker.get_cost_error()
        rejection_rate = (
            self._total_rejections / max(self._total_submissions, 1)
        )

        return {
            "overall_health": self.get_system_health(),
            "worker_load_score": 1.0 - system_load,
            "queue_score": max(0.0, 1.0 - queue_size / max(self.queue_high_water, 1)),
            "cost_model_score": max(0.0, 1.0 - cost_error),
            "rejection_score": 1.0 - rejection_rate,
            "total_submissions": self._total_submissions,
            "total_rejections": self._total_rejections
        }

    def get_gate_stats(self) -> Dict:
        """获取门控统计"""
        return {
            "total_submissions": self._total_submissions,
            "total_rejections": self._total_rejections,
            "rejection_rate": self._total_rejections / max(self._total_submissions, 1),
            "recent_decisions": len(self._decision_history)
        }


# ==================== Scheduler ====================

class Scheduler:
    class Strategy(Enum):
        PRIORITY = "priority"
        SJF = "sjf"
        DEPTH = "depth"
        HYBRID = "hybrid"

    def __init__(self, dag: DAGEngine, cost_tracker: AdaptiveCostTracker = None):
        self.dag = dag
        self.cost_tracker = cost_tracker or AdaptiveCostTracker()

        self._ready_queue: List[Task] = []
        self._delayed_queue: List[Task] = []
        self._running: Dict[str, Task] = {}
        self._completed: Dict[str, Task] = {}
        self._failed: Dict[str, Task] = {}
        self._lock = threading.Lock()

        self.strategy = self.Strategy.HYBRID
        self._scheduling_log: List[SchedulingDecision] = []

        self.load_threshold = DEFAULT_LOAD_THRESHOLD
        self.queue_high_water = DEFAULT_QUEUE_HIGH_WATER

    def set_strategy(self, strategy: Strategy):
        self.strategy = strategy

    def set_load_threshold(self, threshold: float):
        self.load_threshold = max(0.0, min(1.0, threshold))

    def set_high_water(self, water: int):
        self.queue_high_water = water

    def can_dispatch(self, worker_load: float = 0.0) -> bool:
        with self._lock:
            if worker_load >= self.load_threshold:
                return False
            total_pending = len(self._ready_queue) + len(self._delayed_queue)
            if total_pending >= self.queue_high_water:
                return False
            return True

    def get_load_info(self) -> Dict:
        with self._lock:
            return {
                "running": len(self._running),
                "ready": len(self._ready_queue),
                "delayed": len(self._delayed_queue),
                "completed": len(self._completed),
                "load_threshold": self.load_threshold,
                "high_water": self.queue_high_water
            }

    def submit(self, task: Task) -> bool:
        with self._lock:
            task.created_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
            task.estimated_cost = self.cost_tracker.get_estimated_cost(task.agent_type)

            is_ready = self.dag.add_task(task)

            self._log_decision(
                task_id=task.id,
                decision="submitted",
                reason=f"dependencies={len(task.dependencies)}, ready={is_ready}",
                priority=task.priority.value,
                estimated_cost=task.estimated_cost,
                depth=task.depth
            )

            if is_ready:
                task.status = TaskStatus.READY
                self._ready_queue.append(task)
                self._sort_queue()
                return True
            else:
                task.status = TaskStatus.PENDING
                return False

    def dispatch(self, worker_load: float = 0.0) -> Optional[Task]:
        with self._lock:
            if worker_load >= self.load_threshold:
                return None
            if not self._ready_queue:
                return None

            task = self._ready_queue.pop(0)
            task.status = TaskStatus.RUNNING
            task.started_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
            self._running[task.id] = task

            self._log_decision(
                task_id=task.id,
                decision="dispatched",
                reason=f"strategy={self.strategy.value}, worker_load={worker_load:.2f}",
                priority=task.priority.value,
                estimated_cost=task.estimated_cost,
                depth=task.depth
            )

            return task

    def _sort_queue(self):
        if self.strategy == self.Strategy.PRIORITY:
            self._ready_queue.sort(key=lambda t: t.priority.value, reverse=True)
        elif self.strategy == self.Strategy.SJF:
            self._ready_queue.sort(key=lambda t: t.estimated_cost)
        elif self.strategy == self.Strategy.DEPTH:
            self._ready_queue.sort(key=lambda t: (-t.depth, -t.priority.value))
        elif self.strategy == self.Strategy.HYBRID:
            self._ready_queue.sort(key=lambda t: (
                -t.depth, -t.priority.value, t.estimated_cost
            ))

    def _log_decision(
        self,
        task_id: str,
        decision: str,
        reason: str,
        priority: int = 0,
        estimated_cost: float = 0,
        depth: int = 0,
        admitted: bool = True
    ):
        self._scheduling_log.append(SchedulingDecision(
            timestamp=time.time(),
            task_id=task_id,
            decision=decision,
            reason=reason,
            priority=priority,
            estimated_cost=estimated_cost,
            depth=depth,
            admitted=admitted
        ))

    def complete(self, task_id: str, result: Dict, score: float, actual_cost: float = 0.0) -> List[Task]:
        with self._lock:
            if task_id in self._running:
                task = self._running[task_id]
                task.status = TaskStatus.COMPLETE
                task.completed_at = self.dag.clock.value if hasattr(self.dag, 'clock') else 0
                task.result = result
                task.score = score

                if actual_cost > 0 and task.execution_start:
                    task.actual_cost = actual_cost
                    self.cost_tracker.record_actual_cost(
                        task.agent_type, actual_cost, result.get("status") == "success"
                    )

                self._completed[task_id] = task
                del self._running[task_id]

            ready_tasks = self.dag.mark_complete(task_id)
            for t in ready_tasks:
                self._ready_queue.append(t)
            self._sort_queue()

            self._log_decision(
                task_id=task_id,
                decision="completed",
                reason=f"score={score}, actual_cost={actual_cost:.3f}s",
                priority=task.priority.value if task_id in self._completed else 0,
                depth=0
            )

            self._try_restore_delayed()

            return ready_tasks

    def _try_restore_delayed(self):
        if not self._delayed_queue:
            return
        restored = []
        still_delayed = []
        for task in self._delayed_queue:
            if self.dag.is_ready(task.id):
                task.status = TaskStatus.READY
                self._ready_queue.append(task)
                restored.append(task.id)
            else:
                still_delayed.append(task)
        self._delayed_queue = still_delayed
        if restored:
            self._sort_queue()

    def fail(self, task_id: str, error: str) -> None:
        with self._lock:
            if task_id in self._running:
                task = self._running[task_id]
                task.error = error
                if task.retries < task.max_retries:
                    task.status = TaskStatus.PENDING
                    task.retries += 1
                    task.started_at = None
                else:
                    task.status = TaskStatus.FAILED
                    self._failed[task_id] = task
                    self.dag.mark_failed(task_id)
                    del self._running[task_id]

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

    def is_idle(self) -> bool:
        return len(self._ready_queue) == 0 and len(self._running) == 0

    def get_status(self) -> Dict:
        return {
            "ready": len(self._ready_queue),
            "delayed": len(self._delayed_queue),
            "running": len(self._running),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "strategy": self.strategy.value
        }

    def get_scheduling_log(self) -> List[SchedulingDecision]:
        return self._scheduling_log


# ==================== ReusableWorker ====================

class ReusableWorker:
    def __init__(
        self,
        worker_id: str,
        worker_type: WorkerType,
        state_store: StateStore,
        tool_runtime: 'ToolRuntime',
        llm_cache: LLMCache = None
    ):
        self.worker_id = worker_id
        self.worker_type = worker_type
        self.state_store = state_store
        self.tool_runtime = tool_runtime
        self.llm_cache = llm_cache

        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_execution_time = 0.0
        self._last_used: Optional[float] = None

        self._current_load: float = 0.0
        self._capacity: float = 1.0
        self._memory: Dict[str, Any] = {}

        self._context = ExecutionContext(
            agent_id=worker_id,
            allowed_tools=["llm", "verify"],
            max_time=30
        )

    @property
    def is_available(self) -> bool:
        return (
            not self._context.is_killed and
            not self._context.should_stop() and
            self._current_load < self._capacity * 0.95
        )

    @property
    def load(self) -> float:
        return self._current_load

    @property
    def stats(self) -> Dict:
        return {
            "worker_id": self.worker_id,
            "worker_type": self.worker_type.value,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "total_execution_time": self._total_execution_time,
            "avg_execution_time": (
                self._total_execution_time / self._tasks_completed
                if self._tasks_completed > 0 else 0
            ),
            "last_used": self._last_used,
            "load": self._current_load,
            "capacity": self._capacity
        }

    def execute(self, task: Task) -> Dict:
        task.execution_start = time.time()
        self._context.start()
        self._current_load = min(1.0, self._current_load + 0.3)

        self.state_store.log_trace(
            RuntimeEvent.TASK_STARTED, task.id, self.worker_id,
            {"priority": task.priority.value, "depth": task.depth}
        )

        try:
            if self._context.should_stop():
                return self._make_error_result("timeout")

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

            if self._context.should_stop():
                return self._make_error_result("timeout")

            actual_cost = time.time() - task.execution_start
            self._tasks_completed += 1
            self._total_execution_time += actual_cost
            self._last_used = time.time()
            self._current_load = max(0.0, self._current_load - 0.3)
            result["actual_cost"] = actual_cost

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
                {"score": result.get("score", 0), "actual_cost": actual_cost}
            )

            return {
                "status": "success",
                "output": result.get("output"),
                "score": result.get("score", 0),
                "actual_cost": actual_cost
            }

        except Exception as e:
            self._current_load = max(0.0, self._current_load - 0.3)
            self._tasks_failed += 1
            self.state_store.log_trace(
                RuntimeEvent.TASK_FAILED, task.id, self.worker_id,
                {"error": str(e), "traceback": traceback.format_exc()}
            )
            return self._make_error_result(str(e))

    def _make_error_result(self, error: str) -> Dict:
        return {"status": "error", "error": error, "score": 0, "actual_cost": 0.0}

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
        if not self._context.can_use_tool("llm"):
            return f"[Tool denied: llm]"

        if self.llm_cache:
            cached = self.llm_cache.get(prompt, temp)
            if cached:
                return cached

        if self._context.should_stop():
            return "[Timeout]"

        output = llm(prompt, temp)

        if self.llm_cache:
            self.llm_cache.put(prompt, temp, output)

        return output


# ==================== WorkerPool ====================

class WorkerPool:
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
        self._workers: Dict[str, ReusableWorker] = {}
        self._task_to_worker: Dict[str, str] = {}
        self._lock = threading.Lock()

        self._completed_count = 0
        self._failed_count = 0
        self._selection_strategy = "least_loaded"

    def set_selection_strategy(self, strategy: str):
        self._selection_strategy = strategy

    def _get_or_create_worker(self, task: Task) -> Optional[ReusableWorker]:
        with self._lock:
            worker_type = self._get_worker_type(task)

            for worker in self._workers.values():
                if worker.worker_type == worker_type and worker.is_available:
                    return worker

            if len(self._workers) < self.size:
                worker_id = f"worker_{worker_type.value}_{len(self._workers)}"
                worker = ReusableWorker(
                    worker_id=worker_id,
                    worker_type=worker_type,
                    state_store=self.state_store,
                    tool_runtime=self.tool_runtime,
                    llm_cache=self.llm_cache
                )
                self._workers[worker_id] = worker
                return worker

            return self._select_least_loaded_worker(task)

    def _get_worker_type(self, task: Task) -> WorkerType:
        if task.agent_type in ("writer", "editor", "title"):
            return WorkerType.LLM
        elif task.agent_type == "critic":
            return WorkerType.LLM
        else:
            return WorkerType.GENERAL

    def _select_least_loaded_worker(self, task: Task) -> Optional[ReusableWorker]:
        if not self._workers:
            return None

        min_load = float('inf')
        selected = None

        for worker in self._workers.values():
            if worker.is_available and worker.load < min_load:
                min_load = worker.load
                selected = worker

        return selected

    def submit(self, task: Task, scheduler: Scheduler = None) -> bool:
        with self._lock:
            if len(self._futures) >= self.size * 2:
                return False

            worker = self._get_or_create_worker(task)
            if not worker:
                return False

            if worker.load >= 0.95:
                return False

            worker_id = worker.worker_id

            future = self._executor.submit(worker.execute, task)
            self._futures[task.id] = future
            self._task_to_worker[task.id] = worker_id

            self.state_store.log_trace(
                RuntimeEvent.WORKER_SUBMITTED, task.id, worker_id,
                {"pool_size": len(self._futures), "worker_type": worker.worker_type.value, "worker_load": worker.load}
            )

            return True

    def get_completed(self) -> List[Dict]:
        completed = []
        to_remove = []

        with self._lock:
            for task_id, future in self._futures.items():
                if future.done():
                    to_remove.append(task_id)
                    worker_id = self._task_to_worker.get(task_id, "unknown")

                    try:
                        result = future.result(timeout=0)
                        result['task_id'] = task_id
                        result['worker_id'] = worker_id
                        completed.append(result)

                        if result.get("status") == "success":
                            self._completed_count += 1
                        else:
                            self._failed_count += 1

                        self.state_store.log_trace(
                            RuntimeEvent.WORKER_COMPLETE, task_id, worker_id, result
                        )

                    except CancelledError:
                        completed.append({"task_id": task_id, "status": "cancelled", "score": 0})
                    except TimeoutError:
                        pass
                    except Exception as e:
                        self._failed_count += 1
                        completed.append({"task_id": task_id, "status": "error", "error": str(e), "score": 0})

            for task_id in to_remove:
                del self._futures[task_id]
                if task_id in self._task_to_worker:
                    del self._task_to_worker[task_id]

        return completed

    def cancel_all(self):
        with self._lock:
            for future in self._futures.values():
                future.cancel()
            self._futures.clear()
            self._task_to_worker.clear()

    def wait_for(self, timeout: float = None) -> bool:
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

    def get_system_load(self) -> float:
        if not self._workers:
            return 0.0
        total_load = sum(w.load for w in self._workers.values())
        return total_load / len(self._workers)

    def get_worker_stats(self) -> List[Dict]:
        with self._lock:
            return [w.stats for w in self._workers.values()]

    def shutdown(self, wait: bool = True):
        self.cancel_all()
        self._executor.shutdown(wait=wait)

    def get_stats(self) -> Dict:
        return {
            "active": self.active_count,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "workers": len(self._workers),
            "max_workers": self.size,
            "system_load": self.get_system_load(),
            "selection_strategy": self._selection_strategy
        }


# ==================== Tool Runtime ====================

class ToolRuntime:
    def __init__(self, state_store: StateStore):
        self.state_store = state_store
        self.execution_log: List[Dict] = []

    def llm(self, prompt: str, temp: float = 0.8) -> Dict:
        start = time.time()
        try:
            result = llm(prompt, temp)
            self.execution_log.append({"tool": "llm", "elapsed": time.time() - start, "success": True})
            return {"output": result}
        except Exception as e:
            self.execution_log.append({"tool": "llm", "elapsed": time.time() - start, "success": False, "error": str(e)})
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


# ==================== Execution Engine ====================

class ExecutionEngine:
    """
    Execution Engine - v7.5
    ====================
    通过 Execution Gate 统一入口
    """

    def __init__(self, max_workers: int = MAX_WORKERS, deterministic: bool = False):
        self.clock = LogicalClock()
        self.state_store = StateStore(self.clock)
        self.dag = DAGEngine()
        self.cost_tracker = AdaptiveCostTracker()
        self.scheduler = Scheduler(self.dag, self.cost_tracker)
        self.llm_cache = LLMCache(enabled=deterministic)
        self.tool_runtime = ToolRuntime(self.state_store)
        self.worker_pool = WorkerPool(
            self.state_store, self.tool_runtime,
            self.llm_cache, max_workers
        )

        # v7.5 核心：Execution Gate
        self.gate = ExecutionGate(
            scheduler=self.scheduler,
            worker_pool=self.worker_pool,
            cost_tracker=self.cost_tracker,
            state_store=self.state_store
        )

        self.max_iterations = 3
        self.convergence_threshold = 7.5
        self._running = False

    def run(self, initial_task: Task) -> Dict:
        """执行任务（通过 Gate）"""
        self._running = True

        # v7.5：通过 Gate 评估任务
        gate_result = self.gate.evaluate(initial_task)

        if gate_result.decision == GateDecision.REJECT:
            # 任务被拒绝
            self.state_store.log_trace(
                RuntimeEvent.TASK_REJECTED,
                initial_task.id,
                "execution_gate",
                {"reason": gate_result.reason, "health": gate_result.health_score}
            )
            return {
                "best_result": None,
                "best_score": -1,
                "iterations": 0,
                "converged": False,
                "gate_decision": gate_result.decision.value,
                "gate_reason": gate_result.reason,
                "system_health": gate_result.health_score
            }

        elif gate_result.decision == GateDecision.DELAY:
            # 延迟执行
            initial_task.status = TaskStatus.DELAYED
            # 这里简化处理，实际应该放入延迟队列
            pass

        # 正常提交流程
        self.scheduler.submit(initial_task)

        best_result = None
        best_score = -1.0
        iteration = 0

        while self._running and iteration < self.max_iterations:
            iteration += 1

            system_load = self.worker_pool.get_system_load()
            task = self.scheduler.dispatch(worker_load=system_load)

            if task:
                self.worker_pool.submit(task, self.scheduler)
            else:
                if self.scheduler.is_idle() and self.worker_pool.active_count == 0:
                    break

            for result in self.worker_pool.get_completed():
                task_id = result.pop('task_id', None) or result.get('task_id')
                actual_cost = result.get('actual_cost', 0.0)

                if result.get("status") == "success":
                    score = result.get("score", 0)
                    self.scheduler.complete(task_id, result, score, actual_cost)

                    if score > best_score:
                        best_score = score
                        best_result = result

                    self.scheduler.adjust_priority(task_id, score)

                    if score >= self.convergence_threshold:
                        self._running = False
                        break
                else:
                    self.scheduler.fail(task_id, result.get("error", "Unknown"))

            if self.worker_pool.active_count > 0:
                time.sleep(0.01)

        self._running = False

        return {
            "best_result": best_result,
            "best_score": best_score,
            "iterations": iteration,
            "converged": best_score >= self.convergence_threshold,
            "system_health": self.gate.get_system_health()
        }

    def run_feedback_loop(self, writer_task: Task, max_cycles: int = 3) -> Dict:
        best_lyrics = None
        best_score = -1.0

        writer_result = self.run(writer_task)
        if writer_result["best_result"]:
            best_lyrics = writer_result["best_result"].get("output", "")
            best_score = writer_result["best_score"]

        if not best_lyrics:
            return {"best_result": None, "best_score": -1, "cycles": 0}

        for cycle in range(max_cycles):
            if best_score >= self.convergence_threshold:
                break

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
            "scheduler_load": self.scheduler.get_load_info(),
            "worker_pool": self.worker_pool.get_stats(),
            "worker_stats": self.worker_pool.get_worker_stats(),
            "state_store": self.state_store.get_summary(),
            "dag": self.dag.get_summary(),
            "cost_tracker": self.cost_tracker.get_learning_stats(),
            "llm_cache": self.llm_cache.size if self.llm_cache else 0,
            "execution_gate": self.gate.get_health_breakdown()
        }

    def get_scheduling_log(self) -> List[SchedulingDecision]:
        return self.scheduler.get_scheduling_log()

    def shutdown(self):
        self._running = False
        self.worker_pool.shutdown()


# ==================== Agent OS Kernel ====================

class AgentOSKernel:
    """
    Agent OS Kernel - v7.5
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

    def get_scheduling_decisions(self) -> List[SchedulingDecision]:
        return self.engine.get_scheduling_log()

    def get_system_health(self) -> float:
        """获取系统健康度"""
        return self.engine.gate.get_system_health()

    def get_health_breakdown(self) -> Dict:
        """获取健康度明细"""
        return self.engine.gate.get_health_breakdown()

    def shutdown(self):
        self.engine.shutdown()
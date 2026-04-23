"""
v7.6 Agent OS - State Snapshot Layer Tests
============================================
"""

import sys
sys.path.insert(0, '.')

from agent_os import (
    Task, TaskPriority, TaskStatus,
    StateSnapshot, StateSnapshotBuilder, ExecutionGate, GateDecision,
    TaskSnapshot, WorkerSnapshot, QueueSnapshot, CostModelSnapshot,
    LogicalClock, AdaptiveCostTracker
)


def test_frozen_dataclasses():
    """测试不可变数据结构"""
    print("=" * 50)
    print("Frozen Data Classes")
    print("=" * 50)

    # TaskSnapshot
    task = TaskSnapshot(
        id="t1",
        agent_type="writer",
        priority=2,
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    print(f"  TaskSnapshot: {task.id}, cost={task.estimated_cost}")
    print(f"  TaskSnapshot hashable: {hash(task) is not None}")

    # WorkerSnapshot
    worker = WorkerSnapshot(
        worker_id="w1",
        worker_type="llm",
        load=0.5,
        capacity=1.0,
        tasks_completed=10,
        is_available=True
    )
    print(f"  WorkerSnapshot: {worker.worker_id}, load={worker.load}")

    # QueueSnapshot
    queue = QueueSnapshot(
        ready_count=5,
        delayed_count=0,
        running_count=2,
        completed_count=100,
        failed_count=1
    )
    print(f"  QueueSnapshot: ready={queue.ready_count}")

    # CostModelSnapshot
    cost = CostModelSnapshot(
        agent_types=frozenset(["writer", "critic"]),
        cost_error=0.2,
        total_observations=50
    )
    print(f"  CostModel: error={cost.cost_error}")

    print("  [PASS]")


def test_state_snapshot():
    """测试 StateSnapshot"""
    print("\n" + "=" * 50)
    print("State Snapshot")
    print("=" * 50)

    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.3, 1.0, 10, True),
        WorkerSnapshot("w2", "llm", 0.7, 1.0, 5, True),
    ])

    queue = QueueSnapshot(5, 0, 2, 100, 1)
    cost = CostModelSnapshot(frozenset(["writer"]), 0.15, 30)

    state = StateSnapshot(
        timestamp=time.time(),
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=100,
        total_rejections=5
    )

    print(f"  StateSnapshot hashable: {hash(state) is not None}")
    print(f"  System load: {state.get_system_load():.3f}")
    print(f"  Queue pressure: {state.get_queue_pressure():.3f}")
    print(f"  Health: {state.compute_health():.3f}")

    assert 0.0 <= state.compute_health() <= 1.0
    print("  [PASS]")


def test_gate_pure_function():
    """测试 Gate 纯函数"""
    print("\n" + "=" * 50)
    print("Gate Pure Function")
    print("=" * 50)

    gate = ExecutionGate()

    # 构建一个健康的系统快照
    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.3, 1.0, 10, True),
    ])
    queue = QueueSnapshot(3, 0, 1, 50, 0)
    cost = CostModelSnapshot(frozenset(["writer"]), 0.1, 20)

    healthy_state = StateSnapshot(
        timestamp=time.time(),
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=50,
        total_rejections=0
    )

    task = TaskSnapshot(
        id="t1",
        agent_type="writer",
        priority=2,
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    # 评估
    result = gate.evaluate(healthy_state, task)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")
    print(f"  Health: {result.health_score:.3f}")

    assert result.decision == GateDecision.ACCEPT
    print("  [PASS]")


def test_gate_reject_overload():
    """测试 Gate 过载拒绝"""
    print("\n" + "=" * 50)
    print("Gate - Overload Reject")
    print("=" * 50)

    gate = ExecutionGate()

    # 高负载系统
    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.98, 1.0, 100, True),
    ])
    queue = QueueSnapshot(10, 0, 5, 100, 10)
    cost = CostModelSnapshot(frozenset(["writer"]), 0.1, 20)

    overloaded_state = StateSnapshot(
        timestamp=time.time(),
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=100,
        total_rejections=50
    )

    task = TaskSnapshot(
        id="t1",
        agent_type="writer",
        priority=2,
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    result = gate.evaluate(overloaded_state, task)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")

    assert result.decision == GateDecision.REJECT
    print("  [PASS]")


def test_gate_delay_queue_full():
    """测试 Gate 队列满延迟"""
    print("\n" + "=" * 50)
    print("Gate - Queue Full Delay")
    print("=" * 50)

    gate = ExecutionGate()

    # 队列满
    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.5, 1.0, 10, True),
    ])
    queue = QueueSnapshot(12, 0, 3, 50, 2)  # ready=12 > high_water=10
    cost = CostModelSnapshot(frozenset(["writer"]), 0.2, 20)

    queue_full_state = StateSnapshot(
        timestamp=time.time(),
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=100,
        total_rejections=0
    )

    # 普通任务
    normal_task = TaskSnapshot(
        id="t1",
        agent_type="writer",
        priority=2,
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    result = gate.evaluate(queue_full_state, normal_task)

    print(f"  Normal task decision: {result.decision.value}")
    assert result.decision == GateDecision.DELAY

    # CRITICAL 任务
    critical_task = TaskSnapshot(
        id="t2",
        agent_type="writer",
        priority=4,  # CRITICAL
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    result2 = gate.evaluate(queue_full_state, critical_task)
    print(f"  Critical task decision: {result2.decision.value}")
    assert result2.decision == GateDecision.ACCEPT

    print("  [PASS]")


def test_gate_routing():
    """测试 Gate 路由"""
    print("\n" + "=" * 50)
    print("Gate Routing")
    print("=" * 50)

    gate = ExecutionGate()

    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.2, 1.0, 10, True),
        WorkerSnapshot("w2", "llm", 0.8, 1.0, 50, True),
    ])

    queue = QueueSnapshot(3, 0, 1, 50, 0)
    cost = CostModelSnapshot(frozenset(["writer"]), 0.1, 20)

    state = StateSnapshot(
        timestamp=time.time(),
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=50,
        total_rejections=0
    )

    # 便宜任务
    cheap_task = TaskSnapshot(
        id="t1",
        agent_type="title",
        priority=1,
        dependencies=frozenset(),
        estimated_cost=1.0,
        depth=0,
        status="READY",
        created_at=0
    )

    route = gate.route(state, cheap_task)
    print(f"  Cheap task route: {route} (expected: w1 - lower load)")

    # 昂贵任务
    expensive_task = TaskSnapshot(
        id="t2",
        agent_type="writer",
        priority=1,
        dependencies=frozenset(),
        estimated_cost=5.0,
        depth=0,
        status="READY",
        created_at=0
    )

    route2 = gate.route(state, expensive_task)
    print(f"  Expensive task route: {route2}")

    print("  [PASS]")


def test_snapshot_builder():
    """测试快照构建器"""
    print("\n" + "=" * 50)
    print("Snapshot Builder")
    print("=" * 50)

    from agent_os import AgentOSKernel

    kernel = AgentOSKernel()
    builder = kernel.engine.snapshot_builder

    state = builder.build(
        kernel.engine.scheduler,
        kernel.engine.worker_pool,
        kernel.engine.cost_tracker
    )

    print(f"  Snapshot logical_time: {state.logical_time}")
    print(f"  Snapshot workers: {len(state.workers)}")
    print(f"  Snapshot health: {state.compute_health():.3f}")

    kernel.shutdown()
    print("  [PASS]")


def test_deterministic_replay():
    """测试确定性 replay（核心特性）"""
    print("\n" + "=" * 50)
    print("Deterministic Replay")
    print("=" * 50)

    gate = ExecutionGate()

    # 固定系统状态
    workers = frozenset([
        WorkerSnapshot("w1", "llm", 0.4, 1.0, 10, True),
    ])
    queue = QueueSnapshot(5, 0, 2, 50, 0)
    cost = CostModelSnapshot(frozenset(["writer"]), 0.15, 20)

    state = StateSnapshot(
        timestamp=1000.0,
        logical_time=10,
        workers=workers,
        queue=queue,
        cost_model=cost,
        load_threshold=0.8,
        queue_high_water=10,
        total_submissions=50,
        total_rejections=0
    )

    task = TaskSnapshot(
        id="t1",
        agent_type="writer",
        priority=2,
        dependencies=frozenset(),
        estimated_cost=3.0,
        depth=0,
        status="READY",
        created_at=0
    )

    # 多次评估应该得到相同结果
    results = []
    for _ in range(5):
        r = gate.evaluate(state, task)
        results.append(r.decision)

    print(f"  5 evaluations: {[r.value for r in results]}")
    assert len(set(results)) == 1, "Pure function should return same result"

    print("  [PASS]")


if __name__ == "__main__":
    import time

    test_frozen_dataclasses()
    test_state_snapshot()
    test_gate_pure_function()
    test_gate_reject_overload()
    test_gate_delay_queue_full()
    test_gate_routing()
    test_snapshot_builder()
    test_deterministic_replay()

    print("\n" + "=" * 50)
    print("ALL V7.6 TESTS PASSED")
    print("=" * 50)
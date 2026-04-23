"""
v7.5 Agent OS - Execution Gate Tests (No LLM)
==============================================
"""

import sys
sys.path.insert(0, '.')

from agent_os import (
    Task, TaskPriority, TaskStatus,
    DAGEngine, Scheduler, StateStore, LogicalClock,
    AdaptiveCostTracker, ExecutionGate, GateDecision, WorkerType
)


def test_execution_gate_health():
    """测试 System Health Score"""
    print("=" * 50)
    print("Execution Gate - System Health")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)

    # Mock worker pool
    class MockWorkerPool:
        def get_system_load(self): return 0.3
        def get_worker_stats(self): return []

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    health = gate.get_system_health()
    print(f"  Initial health: {health:.3f}")

    breakdown = gate.get_health_breakdown()
    print(f"  Breakdown: {breakdown}")

    assert 0.0 <= health <= 1.0
    print("  [PASS]")


def test_gate_decision_accept():
    """测试 Gate 接受决策"""
    print("\n" + "=" * 50)
    print("Gate Decision - Accept")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)

    class MockWorkerPool:
        def get_system_load(self): return 0.3
        def get_worker_stats(self): return []

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    task = Task(id="t1", agent_type="writer", input_data={}, priority=TaskPriority.NORMAL)
    result = gate.evaluate(task)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")
    print(f"  Health: {result.health_score:.3f}")

    assert result.decision == GateDecision.ACCEPT
    print("  [PASS]")


def test_gate_reject_overload():
    """测试过载拒绝"""
    print("\n" + "=" * 50)
    print("Gate - Overload Reject")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)

    class MockWorkerPool:
        def get_system_load(self): return 0.98

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    task = Task(id="t1", agent_type="writer", input_data={})
    result = gate.evaluate(task)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")

    assert result.decision == GateDecision.REJECT
    print("  [PASS]")


def test_gate_delay_queue_full():
    """测试队列满时延迟"""
    print("\n" + "=" * 50)
    print("Gate - Queue Delay")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)
    scheduler.set_high_water(2)

    class MockWorkerPool:
        def get_system_load(self): return 0.3

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    # Fill queue
    for i in range(3):
        t = Task(id=f"t{i}", agent_type="writer", input_data={}, priority=TaskPriority.NORMAL)
        scheduler.submit(t)

    print(f"  Queue size: {scheduler.get_status()['ready']}")

    task = Task(id="new", agent_type="writer", input_data={})
    result = gate.evaluate(task)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")

    assert result.decision == GateDecision.DELAY
    print("  [PASS]")


def test_gate_critical_priority():
    """测试关键任务绕过"""
    print("\n" + "=" * 50)
    print("Gate - Critical Priority")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)
    scheduler.set_high_water(2)

    class MockWorkerPool:
        def get_system_load(self): return 0.3

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    # Fill queue
    for i in range(3):
        t = Task(id=f"t{i}", agent_type="writer", input_data={}, priority=TaskPriority.NORMAL)
        scheduler.submit(t)

    # Critical task should bypass
    critical = Task(id="critical", agent_type="writer", input_data={}, priority=TaskPriority.CRITICAL)
    result = gate.evaluate(critical)

    print(f"  Decision: {result.decision.value}")
    print(f"  Reason: {result.reason}")

    assert result.decision == GateDecision.ACCEPT
    print("  [PASS]")


def test_health_breakdown():
    """测试健康度明细"""
    print("\n" + "=" * 50)
    print("Health Breakdown")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    cost_tracker = AdaptiveCostTracker()
    dag = DAGEngine()
    scheduler = Scheduler(dag, cost_tracker)

    class MockWorkerPool:
        def get_system_load(self): return 0.4

    gate = ExecutionGate(scheduler, MockWorkerPool(), cost_tracker, state_store)

    # Record some costs
    cost_tracker.record_actual_cost("writer", 2.5, True)
    cost_tracker.record_actual_cost("writer", 3.5, True)

    breakdown = gate.get_health_breakdown()

    print(f"  Overall health: {breakdown['overall_health']:.3f}")
    print(f"  Worker load score: {breakdown['worker_load_score']:.3f}")
    print(f"  Queue score: {breakdown['queue_score']:.3f}")
    print(f"  Cost model score: {breakdown['cost_model_score']:.3f}")
    print(f"  Total submissions: {breakdown['total_submissions']}")
    print(f"  Total rejections: {breakdown['total_rejections']}")

    print("  [PASS]")


def test_system_structure():
    """测试系统结构"""
    print("\n" + "=" * 50)
    print("System Structure v7.5")
    print("=" * 50)

    from agent_os import AgentOSKernel

    kernel = AgentOSKernel()

    state = kernel.get_state()

    print(f"  Execution Gate: {state.get('execution_gate', {})}")
    print(f"  Scheduler: {state['scheduler']}")
    print(f"  Worker Pool: {state['worker_pool']}")

    health = kernel.get_system_health()
    print(f"\n  System health: {health:.3f}")

    kernel.shutdown()

    print("  [PASS]")


if __name__ == "__main__":
    test_execution_gate_health()
    test_gate_decision_accept()
    test_gate_reject_overload()
    test_gate_delay_queue_full()
    test_gate_critical_priority()
    test_health_breakdown()
    test_system_structure()

    print("\n" + "=" * 50)
    print("ALL V7.5 TESTS PASSED")
    print("=" * 50)
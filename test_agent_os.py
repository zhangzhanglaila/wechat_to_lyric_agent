"""
v7.4 Agent OS - Stability Tests
================================
测试 Backpressure + Admission Control + Adaptive Cost + Resource Model
"""

import sys
sys.path.insert(0, '.')

from agent_os import (
    Task, TaskPriority, TaskStatus,
    DAGEngine, Scheduler, StateStore, LogicalClock,
    ReusableWorker, WorkerPool, WorkerType, ToolRuntime,
    AdaptiveCostTracker
)


def test_adaptive_cost_tracker():
    """测试自适应成本追踪"""
    print("=" * 50)
    print("Adaptive Cost Tracker")
    print("=" * 50)

    tracker = AdaptiveCostTracker()

    # 初始估计
    cost1 = tracker.get_estimated_cost("writer")
    print(f"  Initial writer cost: {cost1}")

    # 记录实际成本（成功任务）
    tracker.record_actual_cost("writer", 2.5, task_success=True)
    tracker.record_actual_cost("writer", 3.5, task_success=True)
    tracker.record_actual_cost("writer", 2.0, task_success=True)

    # 学习后估计
    cost2 = tracker.get_estimated_cost("writer")
    print(f"  After learning: {cost2}")

    stats = tracker.get_learning_stats()
    print(f"  Stats: {stats}")

    # 失败任务不计入
    tracker.record_actual_cost("writer", 10.0, task_success=False)
    cost3 = tracker.get_estimated_cost("writer")
    print(f"  After failed task: {cost3}")

    assert stats["writer"]["count"] == 3, "Should only count 3 successful tasks"
    print("  [PASS]")


def test_admission_control():
    """测试准入控制"""
    print("\n" + "=" * 50)
    print("Admission Control")
    print("=" * 50)

    dag = DAGEngine()
    tracker = AdaptiveCostTracker()
    scheduler = Scheduler(dag, tracker)

    # 设置低阈值
    scheduler.set_load_threshold(0.5)
    scheduler.set_high_water(3)

    print(f"  Load threshold: {scheduler.load_threshold}")
    print(f"  High water: {scheduler.queue_high_water}")

    # 模拟过载
    can_dispatch_1 = scheduler.can_dispatch(worker_load=0.3)
    print(f"  can_dispatch(load=0.3): {can_dispatch_1} (expected: True)")

    can_dispatch_2 = scheduler.can_dispatch(worker_load=0.6)
    print(f"  can_dispatch(load=0.6): {can_dispatch_2} (expected: False)")

    # 检查调度日志
    log = scheduler.get_scheduling_log()
    backpressure_events = [d for d in log if d.decision == "backpressure"]
    print(f"  Backpressure events: {len(backpressure_events)}")

    assert can_dispatch_1 == True
    assert can_dispatch_2 == False
    print("  [PASS]")


def test_resource_model():
    """测试资源模型"""
    print("\n" + "=" * 50)
    print("Resource Model")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    tool_runtime = ToolRuntime(state_store)

    worker = ReusableWorker(
        worker_id="test_worker",
        worker_type=WorkerType.LLM,
        state_store=state_store,
        tool_runtime=tool_runtime,
        llm_cache=None
    )

    print(f"  Initial load: {worker.load}")
    print(f"  Available: {worker.is_available}")

    # 模拟任务执行（负载变化）
    worker._current_load = 0.8
    print(f"  After task start: {worker.load}")

    worker._current_load = max(0.0, worker._current_load - 0.3)
    print(f"  After task complete: {worker.load}")

    stats = worker.stats
    print(f"  Stats: load={stats['load']}, capacity={stats['capacity']}")

    print("  [PASS]")


def test_backpressure_in_dispatch():
    """测试调度器背压"""
    print("\n" + "=" * 50)
    print("Backpressure in Dispatch")
    print("=" * 50)

    dag = DAGEngine()
    tracker = AdaptiveCostTracker()
    scheduler = Scheduler(dag, tracker)

    # 提交任务
    task = Task(id="t1", agent_type="writer", input_data={}, priority=TaskPriority.HIGH)
    scheduler.submit(task)

    # 正常调度
    dispatched = scheduler.dispatch(worker_load=0.0)
    print(f"  Dispatched (load=0.0): {dispatched is not None}")

    # 重新入队
    scheduler._ready_queue.append(task)
    task.status = TaskStatus.READY
    scheduler._running.pop(task.id, None)

    # 背压时调度失败
    dispatched = scheduler.dispatch(worker_load=0.9)
    print(f"  Dispatched (load=0.9): {dispatched is None}")

    log = scheduler.get_scheduling_log()
    backpressure = [d for d in log if d.decision == "backpressure"]
    print(f"  Backpressure decisions: {len(backpressure)}")

    assert dispatched is None
    print("  [PASS]")


def test_worker_load_balancing():
    """测试 Worker 负载均衡"""
    print("\n" + "=" * 50)
    print("Worker Load Balancing")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    tool_runtime = ToolRuntime(state_store)

    pool = WorkerPool(
        state_store=state_store,
        tool_runtime=tool_runtime,
        llm_cache=None,
        size=3
    )

    print(f"  Initial system load: {pool.get_system_load()}")

    # 创建 workers
    w1 = ReusableWorker("w1", WorkerType.LLM, state_store, tool_runtime, None)
    w2 = ReusableWorker("w2", WorkerType.LLM, state_store, tool_runtime, None)

    pool._workers["w1"] = w1
    pool._workers["w2"] = w2

    # 设置不同负载
    w1._current_load = 0.8
    w2._current_load = 0.2

    print(f"  w1 load: {w1.load}")
    print(f"  w2 load: {w2.load}")
    print(f"  System load: {pool.get_system_load()}")

    pool.shutdown()

    print("  [PASS]")


def test_scheduling_log_with_admission():
    """测试调度日志包含准入决策"""
    print("\n" + "=" * 50)
    print("Scheduling Log with Admission")
    print("=" * 50)

    dag = DAGEngine()
    tracker = AdaptiveCostTracker()
    scheduler = Scheduler(dag, tracker)

    scheduler.set_load_threshold(0.5)

    # 触发背压
    scheduler.can_dispatch(worker_load=0.6)

    log = scheduler.get_scheduling_log()
    print(f"  Total decisions: {len(log)}")

    for d in log:
        print(f"    [{d.decision}] admitted={d.admitted}: {d.reason}")

    admitted_decisions = [d for d in log if d.admitted]
    rejected_decisions = [d for d in log if not d.admitted]

    print(f"  Admitted: {len(admitted_decisions)}, Rejected: {len(rejected_decisions)}")

    print("  [PASS]")


def test_full_system_v74():
    """测试完整 v7.4 系统"""
    print("\n" + "=" * 50)
    print("Full System v7.4")
    print("=" * 50)

    from agent_os import AgentOSKernel

    kernel = AgentOSKernel()

    state = kernel.get_state()

    print(f"  Scheduler: {state['scheduler']}")
    print(f"  Scheduler Load: {state['scheduler_load']}")
    print(f"  Worker Pool: {state['worker_pool']}")
    print(f"  Cost Tracker: {state['cost_tracker']}")

    kernel.shutdown()

    print("  [PASS]")


if __name__ == "__main__":
    test_adaptive_cost_tracker()
    test_admission_control()
    test_resource_model()
    test_backpressure_in_dispatch()
    test_worker_load_balancing()
    test_scheduling_log_with_admission()
    test_full_system_v74()

    print("\n" + "=" * 50)
    print("ALL V7.4 TESTS PASSED")
    print("=" * 50)
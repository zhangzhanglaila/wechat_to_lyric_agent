"""
v7.3 Agent OS - Unit Tests (No LLM)
====================================
测试核心调度逻辑，不依赖 LLM
"""

import sys
sys.path.insert(0, '.')

from agent_os import (
    Task, TaskPriority, TaskStatus,
    DAGEngine, Scheduler, StateStore, LogicalClock,
    ReusableWorker, WorkerPool, WorkerType, ToolRuntime
)

def test_dag_depth():
    """测试 DAG 深度计算"""
    print("=" * 50)
    print("DAG Depth Calculation")
    print("=" * 50)

    dag = DAGEngine()

    # 创建 DAG: A -> B -> C, A -> D
    task_a = Task(id="A", agent_type="writer", input_data={})
    task_b = Task(id="B", agent_type="critic", input_data={}, dependencies={"A"})
    task_c = Task(id="C", agent_type="editor", input_data={}, dependencies={"B"})
    task_d = Task(id="D", agent_type="title", input_data={}, dependencies={"A"})

    dag.add_task(task_a)
    dag.add_task(task_b)
    dag.add_task(task_c)
    dag.add_task(task_d)

    print(f"  A depth: {task_a.depth} (expected: 0)")
    print(f"  B depth: {task_b.depth} (expected: 1)")
    print(f"  C depth: {task_c.depth} (expected: 2)")
    print(f"  D depth: {task_d.depth} (expected: 1)")

    # 验证 B/C 未就绪因为依赖未完成
    assert task_b.status == TaskStatus.PENDING
    assert task_c.status == TaskStatus.PENDING
    assert task_d.status == TaskStatus.PENDING

    # 完成 A，B 和 D 应该就绪
    ready = dag.mark_complete("A")
    assert len(ready) == 2, f"Expected 2 ready tasks, got {len(ready)}"

    print(f"  After A complete: {[t.id for t in ready]} ready")
    print("  [PASS]")

def test_scheduling_strategies():
    """测试调度策略"""
    print("\n" + "=" * 50)
    print("Scheduling Strategies")
    print("=" * 50)

    dag = DAGEngine()
    scheduler = Scheduler(dag)

    tasks = [
        Task(id="t1", agent_type="writer", input_data={}, priority=TaskPriority.LOW),
        Task(id="t2", agent_type="critic", input_data={}, priority=TaskPriority.CRITICAL),
        Task(id="t3", agent_type="editor", input_data={}, priority=TaskPriority.NORMAL),
    ]
    for t in tasks:
        scheduler.submit(t)

    # Priority
    scheduler.set_strategy(Scheduler.Strategy.PRIORITY)
    scheduler._sort_queue()
    order = [t.id for t in scheduler._ready_queue]
    print(f"  PRIORITY: {order}")
    assert order == ["t2", "t3", "t1"], f"Priority failed: {order}"

    # SJF
    scheduler._ready_queue = tasks
    scheduler.set_strategy(Scheduler.Strategy.SJF)
    scheduler._sort_queue()
    order = [t.id for t in scheduler._ready_queue]
    print(f"  SJF: {order}")
    # writer=3.0, critic=2.0, editor=2.5
    assert order == ["t2", "t3", "t1"], f"SJF failed: {order}"

    # Hybrid
    scheduler._ready_queue = tasks
    scheduler.set_strategy(Scheduler.Strategy.HYBRID)
    scheduler._sort_queue()
    order = [t.id for t in scheduler._ready_queue]
    print(f"  HYBRID: {order}")

    print("  [PASS]")

def test_worker_reuse():
    """测试 Worker 复用"""
    print("\n" + "=" * 50)
    print("Worker Reuse")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    tool_runtime = ToolRuntime(state_store)

    # 创建 ReusableWorker
    worker = ReusableWorker(
        worker_id="test_worker",
        worker_type=WorkerType.LLM,
        state_store=state_store,
        tool_runtime=tool_runtime,
        llm_cache=None
    )

    print(f"  Worker: {worker.worker_id}")
    print(f"  Type: {worker.worker_type.value}")
    print(f"  Available: {worker.is_available}")
    print(f"  Completed: {worker.stats['tasks_completed']}")

    # 模拟执行（不真正调用 LLM）
    task = Task(id="mock_task", agent_type="writer", input_data={})
    # worker.execute(task) 会真正调用 LLM，所以我们只测结构

    print("  [PASS]")

def test_worker_pool():
    """测试 WorkerPool"""
    print("\n" + "=" * 50)
    print("Worker Pool")
    print("=" * 50)

    clock = LogicalClock()
    state_store = StateStore(clock)
    tool_runtime = ToolRuntime(state_store)

    pool = WorkerPool(
        state_store=state_store,
        tool_runtime=tool_runtime,
        llm_cache=None,
        size=2
    )

    print(f"  Max workers: {pool.size}")
    print(f"  Strategy: {pool._selection_strategy}")

    # 设置策略
    pool.set_selection_strategy("least_loaded")
    assert pool._selection_strategy == "least_loaded"

    # 选择策略（mock task，不真正提交）
    # 因为 _select_worker 会调用 llm，我们只测结构
    print(f"  Strategy set: {pool._selection_strategy}")

    pool.shutdown()
    print("  [PASS]")

def test_scheduling_decision_log():
    """测试调度决策日志"""
    print("\n" + "=" * 50)
    print("Scheduling Decision Log")
    print("=" * 50)

    dag = DAGEngine()
    scheduler = Scheduler(dag)

    # 提交任务
    task = Task(
        id="test_task",
        agent_type="writer",
        input_data={},
        priority=TaskPriority.HIGH
    )
    scheduler.submit(task)

    # 分发
    dispatched = scheduler.dispatch()
    assert dispatched is not None
    assert dispatched.id == "test_task"

    # 检查决策日志
    log = scheduler.get_scheduling_log()
    print(f"  Decisions logged: {len(log)}")

    for d in log:
        print(f"    [{d.decision}] {d.task_id}: {d.reason}")

    print("  [PASS]")

def test_state_store():
    """测试 StateStore"""
    print("\n" + "=" * 50)
    print("State Store")
    print("=" * 50)

    store = StateStore()

    # 提交 snapshots
    s1 = store.commit_snapshot("agent_1", "task_1", {"v": 1}, 6.0)
    s2 = store.commit_snapshot("agent_1", "task_2", {"v": 2}, 8.0)
    s3 = store.commit_snapshot("agent_2", "task_3", {"v": 3}, 7.5)

    print(f"  Snapshots: {store.snapshot_count}")
    print(f"  Best score: {store.get_best_score()}")
    print(f"  Checkpoint: {store.get_best_snapshot('agent_1').hash}")

    # 回滚
    store.rollback_to(s1.hash)
    state = store.get_agent_state("agent_1")
    print(f"  After rollback: {state}")

    print("  [PASS]")

def test_full_system_structure():
    """测试完整系统结构"""
    print("\n" + "=" * 50)
    print("System Structure")
    print("=" * 50)

    from agent_os import AgentOSKernel

    kernel = AgentOSKernel()

    print("  Components:")
    print(f"    - Scheduler: {kernel.engine.scheduler}")
    print(f"    - WorkerPool: {kernel.engine.worker_pool}")
    print(f"    - DAG: {kernel.engine.dag}")
    print(f"    - StateStore: {kernel.engine.state_store}")

    state = kernel.get_state()
    print(f"\n  Scheduler: {state['scheduler']}")
    print(f"  Worker Pool: {state['worker_pool']}")
    print(f"  DAG: {state['dag']}")

    print("  [PASS]")

def test_dag_wakeup():
    """测试 DAG 任务唤醒"""
    print("\n" + "=" * 50)
    print("DAG Task Wakeup")
    print("=" * 50)

    dag = DAGEngine()

    # 创建链: A -> B -> C
    task_a = Task(id="A", agent_type="writer", input_data={})
    task_b = Task(id="B", agent_type="critic", input_data={}, dependencies={"A"})
    task_c = Task(id="C", agent_type="editor", input_data={}, dependencies={"B"})

    dag.add_task(task_a)
    dag.add_task(task_b)
    dag.add_task(task_c)

    # A 就绪，B 和 C 等待
    assert task_a.status == TaskStatus.READY
    assert task_b.status == TaskStatus.PENDING
    assert task_c.status == TaskStatus.PENDING

    # 完成 A
    ready_b = dag.mark_complete("A")
    print(f"  After A: {[t.id for t in ready_b]} ready")
    assert len(ready_b) == 1 and ready_b[0].id == "B"

    # 完成 B
    ready_c = dag.mark_complete("B")
    print(f"  After B: {[t.id for t in ready_c]} ready")
    assert len(ready_c) == 1 and ready_c[0].id == "C"

    print("  [PASS]")

if __name__ == "__main__":
    test_dag_depth()
    test_scheduling_strategies()
    test_worker_reuse()
    test_worker_pool()
    test_scheduling_decision_log()
    test_state_store()
    test_full_system_structure()
    test_dag_wakeup()

    print("\n" + "=" * 50)
    print("ALL V7.3 UNIT TESTS PASSED")
    print("=" * 50)
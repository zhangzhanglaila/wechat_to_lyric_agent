"""
v7.2 Agent OS - Integration Test
==================================
测试闭环执行：DAG + WorkerPool + Scheduler 回流
"""

import sys
sys.path.insert(0, '.')

from agent_os import (
    AgentOSKernel, Task, TaskPriority, TaskStatus,
    DAGEngine, Scheduler, WorkerPool, StateStore,
    LogicalClock, LLMCache, ExecutionContext
)

def test_dag_readiness():
    """测试 DAG readiness 修复"""
    print("=" * 60)
    print("DAG Readiness Test (Critical Fix)")
    print("=" * 60)

    dag = DAGEngine()

    # 创建依赖链: A → B → C
    task_a = Task(id="A", agent_type="writer", input_data={})
    task_b = Task(id="B", agent_type="critic", input_data={}, dependencies={"A"})
    task_c = Task(id="C", agent_type="editor", input_data={}, dependencies={"B"})

    # A 就绪
    ready_a = dag.add_task(task_a)
    print(f"Task A ready: {ready_a} (expected: True)")

    # B, C 不就绪
    ready_b = dag.add_task(task_b)
    ready_c = dag.add_task(task_c)
    print(f"Task B ready: {ready_b} (expected: False)")
    print(f"Task C ready: {ready_c} (expected: False)")

    # 完成 A
    ready_after_a = dag.mark_complete("A")
    print(f"After A complete, ready tasks: {[t.id for t in ready_after_a]} (expected: ['B'])")

    # 完成 B
    ready_after_b = dag.mark_complete("B")
    print(f"After B complete, ready tasks: {[t.id for t in ready_after_b]} (expected: ['C'])")

    # 验证
    assert ready_a == True, "A should be ready"
    assert ready_b == False, "B should NOT be ready (depends on A)"
    assert ready_c == False, "C should NOT be ready (depends on B)"
    assert len(ready_after_a) == 1 and ready_after_a[0].id == "B", "B should be ready after A"
    assert len(ready_after_b) == 1 and ready_after_b[0].id == "C", "C should be ready after B"

    print("\n[PASS] DAG readiness fix verified!")

def test_scheduler_worker_loop():
    """测试 Scheduler ↔ WorkerPool 闭环"""
    print("\n" + "=" * 60)
    print("Scheduler <=> WorkerPool Loop Test")
    print("=" * 60)

    clock = LogicalClock()
    state_store = StateStore(clock)
    dag = DAGEngine()
    scheduler = Scheduler(dag)

    from agent_os import ToolRuntime
    tool_runtime = ToolRuntime(state_store)
    llm_cache = LLMCache(enabled=False)

    pool = WorkerPool(state_store, tool_runtime, llm_cache, size=2)

    # 提交任务
    task1 = Task(id="t1", agent_type="writer", input_data={})
    scheduler.submit(task1)

    print(f"After submit: ready={scheduler.get_status()['ready']}")

    # Dispatch
    dispatched = scheduler.dispatch()
    print(f"Dispatched: {dispatched.id if dispatched else None}")

    # 模拟 worker 执行并提交结果
    pool.submit(dispatched, scheduler)

    # 收集结果
    results = pool.get_completed()
    print(f"Collected results: {len(results)}")

    # ✅ 关键：回流到 scheduler
    for result in results:
        task_id = result.get('task_id')
        if task_id:
            scheduler.complete(task_id, result, result.get('score', 0))

    print(f"After complete: {scheduler.get_status()}")

    pool.shutdown()

def test_deterministic_mode():
    """测试 Deterministic 模式"""
    print("\n" + "=" * 60)
    print("Deterministic Mode Test")
    print("=" * 60)

    kernel = AgentOSKernel(deterministic=True)

    print(f"LLM Cache enabled: {kernel.engine.llm_cache.enabled}")

    # 相同输入应该得到相同结果（如果 cache 命中）
    # 这里只是验证组件存在
    print("[PASS] Deterministic mode initialized")

def test_execution_loop():
    """测试完整执行闭环"""
    print("\n" + "=" * 60)
    print("Execution Loop Test")
    print("=" * 60)

    kernel = AgentOSKernel(max_workers=2)

    # 简单任务
    task = Task(
        id="simple_001",
        agent_type="writer",
        input_data={"emotion": "测试", "style": "伤感"},
        priority=TaskPriority.NORMAL
    )

    result = kernel.execute_task(task)

    print(f"\n[Result]")
    print(f"  Best Score: {result['best_score']}")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Converged: {result.get('converged', False)}")

    state = kernel.get_state()
    print(f"\n[System State]")
    print(f"  Scheduler: {state['scheduler']}")
    print(f"  Worker Pool: {state['worker_pool']}")
    print(f"  DAG: {state['dag']}")
    print(f"  LLM Cache: {state.get('llm_cache', 0)}")

    kernel.shutdown()

def test_full_feedback_loop():
    """完整 feedback loop 测试"""
    print("\n" + "=" * 60)
    print("Full Feedback Loop Test")
    print("=" * 60)

    kernel = AgentOSKernel()

    writer_task = Task(
        id="writer_001",
        agent_type="writer",
        input_data={
            "emotion": "伤感",
            "emotion_detail": "分手后的孤独",
            "keywords": ["回忆", "眼泪", "黑夜", "孤独"],
            "story": "分手后的独白",
            "style": "伤感"
        },
        priority=TaskPriority.HIGH
    )

    print("\n[Step 1] Writer generating lyrics...")
    result = kernel.run_feedback_loop(writer_task, max_cycles=2)

    print(f"\n[Result]")
    print(f"  Best Score: {result['best_score']}")
    print(f"  Cycles: {result['cycles']}")
    print(f"  Converged: {result.get('converged', False)}")

    if result['best_result']:
        lyrics = result['best_result'].get('output', '')
        print(f"\n[Generated Lyrics] ({len(lyrics)} chars)")
        print("-" * 40)
        print(lyrics[:300] if len(lyrics) > 300 else lyrics)

    print("\n[System State]")
    state = kernel.get_state()
    print(f"  Scheduler: {state['scheduler']}")
    print(f"  DAG: {state['dag']}")

    kernel.shutdown()

if __name__ == "__main__":
    test_dag_readiness()
    test_scheduler_worker_loop()
    test_deterministic_mode()
    test_execution_loop()
    test_full_feedback_loop()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
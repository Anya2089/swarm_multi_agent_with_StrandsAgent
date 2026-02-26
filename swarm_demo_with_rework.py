"""
Swarm Multi-Agent Demo with Rework Mechanism
支持返工的多智能体协作示例

当 reviewer 发现问题时，可以将任务交回给前序 Agent 进行修复
"""
import logging
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import Swarm

# 开启详细日志
logging.getLogger("strands.multiagent").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# Bedrock Claude 模型配置
model = BedrockModel(
    model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-west-2"
)

# ========== 创建支持返工的 Agent ==========

researcher = Agent(
    name="researcher",
    model=model,
    system_prompt="""You are a research specialist.
    
Your responsibilities:
1. Gather and analyze requirements
2. Research best practices and industry standards
3. Document clear, actionable requirements

When your research is complete, hand off to the architect.
If you receive feedback from reviewer about missing requirements, address them and hand off again."""
)

architect = Agent(
    name="architect", 
    model=model,
    system_prompt="""You are a system architect.

Your responsibilities:
1. Design system architecture based on requirements
2. Define API endpoints, data models, and system components
3. Ensure the design follows best practices

When design is complete, hand off to the coder.
If you receive feedback from reviewer about design issues, revise your design and hand off again."""
)

coder = Agent(
    name="coder",
    model=model,
    system_prompt="""You are a coding specialist.

Your responsibilities:
1. Implement code based on the architecture design
2. Follow coding best practices
3. Include proper error handling and validation

When implementation is complete, hand off to the reviewer.
If you receive feedback from reviewer about code issues, fix them and hand off again."""
)

# 关键：reviewer 可以将任务交回给前序 Agent
reviewer = Agent(
    name="reviewer",
    model=model,
    system_prompt="""You are a senior code reviewer.

Your responsibilities:
1. Review code against requirements and architecture
2. Check for bugs, security issues, and best practices
3. Verify the implementation meets all requirements

Review criteria:
- Code correctness and bug-free
- Follows the architecture design
- Proper error handling
- Security best practices
- Code quality and readability

After review:
- If you find CODE issues (bugs, missing error handling, security problems):
  → Hand off to "coder" with specific issues to fix
  
- If you find ARCHITECTURE issues (wrong design, missing components):
  → Hand off to "architect" with specific design problems
  
- If you find REQUIREMENT issues (missing features, unclear specs):
  → Hand off to "researcher" to clarify requirements

- If everything looks good:
  → Provide final approval and summary WITHOUT handing off

Be strict but fair. Only approve if the code truly meets all requirements."""
)

# 创建 Swarm，配置支持返工
swarm = Swarm(
    [researcher, architect, coder, reviewer],
    max_handoffs=15,        # 允许更多交接以支持返工
    max_iterations=20,      # 允许更多迭代
    # 乒乓检测：最近 6 次交接中至少要有 2 个不同的 Agent
    repetitive_handoff_detection_window=6,
    repetitive_handoff_min_unique_agents=2
)

# 执行一个稍微复杂的任务，更容易触发返工
task = """Design and implement a REST API for a todo app with the following requirements:
1. CRUD operations for todos
2. User authentication (JWT)
3. Input validation
4. Proper error responses with status codes
5. Pagination for list endpoints"""

print("="*60)
print("🚀 Starting Swarm with Rework Mechanism")
print("="*60)
print(f"\nTask: {task}\n")

result = swarm(task)

# ========== 输出结果 ==========

print("\n" + "="*60)
print("📊 执行结果概览")
print("="*60)
print(f"状态: {result.status}")
print(f"总执行时间: {result.execution_time}ms")
print(f"总迭代次数: {result.execution_count}")

print("\n" + "="*60)
print("🔄 Agent 执行顺序（含返工）")
print("="*60)
agent_sequence = [node.node_id for node in result.node_history]
print(" → ".join(agent_sequence))

# 统计每个 Agent 被调用的次数
from collections import Counter
agent_counts = Counter(agent_sequence)
print("\n各 Agent 调用次数:")
for agent, count in agent_counts.items():
    rework_indicator = " (有返工)" if count > 1 else ""
    print(f"  {agent}: {count} 次{rework_indicator}")

print("\n" + "="*60)
print("📝 各 Agent 最终输出")
print("="*60)
for agent_name, agent_result in result.results.items():
    print(f"\n【{agent_name}】")
    print("-" * 40)
    if hasattr(agent_result, 'result') and agent_result.result:
        output = str(agent_result.result)[:800]
        print(output)
        if len(str(agent_result.result)) > 800:
            print("... (truncated)")

print("\n" + "="*60)
print("💰 Token 使用统计")
print("="*60)
if result.accumulated_usage:
    print(f"Input tokens: {result.accumulated_usage.get('inputTokens', 'N/A')}")
    print(f"Output tokens: {result.accumulated_usage.get('outputTokens', 'N/A')}")

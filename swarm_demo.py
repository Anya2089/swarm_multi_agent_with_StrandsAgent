import logging
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import Swarm

# 开启详细日志，能看到 Agent 间的交接过程
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

# 创建专业化 Agent
researcher = Agent(
    name="researcher",
    model=model,
    system_prompt="""You are a research specialist. 
    Gather requirements and research best practices.
    When research is complete, hand off to the architect."""
)

architect = Agent(
    name="architect", 
    model=model,
    system_prompt="""You are a system architect.
    Design the system architecture based on research.
    When design is complete, hand off to the coder."""
)

coder = Agent(
    name="coder",
    model=model,
    system_prompt="""You are a coding specialist.
    Implement code based on the architecture.
    When done, hand off to the reviewer."""
)

reviewer = Agent(
    name="reviewer",
    model=model,
    system_prompt="""You are a code reviewer.
    Review and provide final solution. You are the last agent."""
)

# 创建 Swarm（第一个 Agent 就是入口）
swarm = Swarm(
    [researcher, architect, coder, reviewer],
    max_handoffs=10,
    max_iterations=15
)

# 执行
result = swarm("Design a simple REST API for a todo app")

# ========== 观察运行效果 ==========

# 1. 整体状态
print("\n" + "="*50)
print("📊 执行结果概览")
print("="*50)
print(f"状态: {result.status}")
print(f"总执行时间: {result.execution_time}ms")
print(f"总迭代次数: {result.execution_count}")

# 2. Agent 执行顺序（核心：看交接流程）
print("\n" + "="*50)
print("🔄 Agent 执行顺序")
print("="*50)
agent_sequence = [node.node_id for node in result.node_history]
print(" → ".join(agent_sequence))

# 3. 每个 Agent 的输出
print("\n" + "="*50)
print("📝 各 Agent 输出详情")
print("="*50)
for agent_name, agent_result in result.results.items():
    print(f"\n【{agent_name}】")
    print("-" * 30)
    if hasattr(agent_result, 'result') and agent_result.result:
        output = str(agent_result.result)[:500]
        print(output)
        if len(str(agent_result.result)) > 500:
            print("... (truncated)")

# 4. Token 使用统计
print("\n" + "="*50)
print("💰 Token 使用统计")
print("="*50)
if result.accumulated_usage:
    print(f"Input tokens: {result.accumulated_usage.get('inputTokens', 'N/A')}")
    print(f"Output tokens: {result.accumulated_usage.get('outputTokens', 'N/A')}")

# 5. 最终结果
print("\n" + "="*50)
print("✅ 最终输出")
print("="*50)
print(result.result)

# Strands Agents Swarm 多智能体协作机制详解

## 1. 什么是 Swarm

Swarm 是 Strands Agents SDK 提供的一种多智能体协作模式，核心理念是"涌现智能"（Emergent Intelligence）——多个专业化的 Agent 通过自主协作，共同完成复杂任务。

### 核心特点

| 特性 | 说明 |
|------|------|
| 去中心化 | 没有中央调度器，Agent 之间直接协作 |
| 自主交接 | 每个 Agent 自己决定何时把任务交给谁 |
| 共享上下文 | 所有 Agent 都能看到完整的任务背景和历史 |
| 共享知识 | Agent 的工作成果可以累积传递 |

### 术语说明

在 Swarm 中有两个容易混淆的概念，这里做一个明确区分：

| 术语 | 源码实现 | 说明 |
|------|----------|------|
| **共享上下文（Full Context）** | `_build_node_input()` 构建的完整输入 | 包含：原始任务、交接消息、执行历史、共享知识、可用Agent列表 |
| **共享知识（Shared Knowledge）** | `SharedContext.context` | 仅指 Agent 通过 `handoff_to_agent` 的 `context` 参数传递的结构化数据 |

简单来说：
- **共享上下文** = 完整的输入信息（大概念）
- **共享知识** = Agent 主动传递的工作成果（小概念，是共享上下文的一部分）

```
共享上下文（Full Context）
├── Handoff Message: 交接消息
├── User Request: 原始任务
├── Previous agents: 执行历史
├── Shared knowledge: 共享知识 ← 这就是 context 参数传递的数据
│   ├── researcher: {...}
│   ├── architect: {...}
│   └── coder: {...}
└── Other agents: 可用Agent列表
```

### 与传统模式对比

```
传统 Orchestrator 模式：              Swarm 去中心化模式：
                                      
    Orchestrator                      Agent A ←→ Agent B
    ↓ 分配任务                            ↖    ↗
    Agent A → 返回 → Orchestrator          Agent C
    ↓ 分配任务                        
    Agent B → 返回 → Orchestrator      每个 Agent 平等，自主决策
    ↓ 汇总                            无需中央控制
```

### 返工机制

Swarm 支持任意方向的交接，不仅可以向前传递，也可以向后返工。例如 reviewer 发现问题时，可以将任务交回给 coder 或 architect 进行修复。

```
正常流程：
researcher → architect → coder → reviewer → 完成

返工流程（reviewer 发现代码问题）：
researcher → architect → coder → reviewer → coder → reviewer → 完成
                                    ↑          ↓
                                    └──── 返工 ────┘
```

返工机制的关键在于 **system prompt 的设计**，需要明确告诉 Agent 在什么情况下应该交回给谁：

```python
reviewer = Agent(
    name="reviewer",
    model=model,
    system_prompt="""You are a code reviewer.
    
    If you find issues:
    - Code bugs → hand off back to coder
    - Architecture flaws → hand off back to architect
    - Missing requirements → hand off back to researcher
    
    Only if everything looks good, provide final solution without handing off."""
)
```

---

## 2. 代码架构设计

### 2.1 基础结构

```python
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import Swarm

# 1. 配置 LLM 模型
model = BedrockModel(
    model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-west-2"
)

# 2. 创建专业化 Agent
researcher = Agent(
    name="researcher",
    model=model,
    system_prompt="You are a research specialist..."
)

architect = Agent(name="architect", model=model, system_prompt="...")
coder = Agent(name="coder", model=model, system_prompt="...")
reviewer = Agent(name="reviewer", model=model, system_prompt="...")

# 3. 组建 Swarm
swarm = Swarm(
    [researcher, architect, coder, reviewer],  # 列表第一个 Agent 就是入口
    max_handoffs=10,      # 最大交接次数
    max_iterations=15     # 最大迭代次数
)

# 4. 执行任务
result = swarm("Design a simple REST API for a todo app")
```

### 2.2 入口 Agent 的确定方式

Swarm 的入口 Agent 由 **列表顺序** 决定——第一个 Agent 就是入口：

```python
# researcher 作为入口（列表第一个）
swarm = Swarm([researcher, architect, coder, reviewer], ...)

# 如果想让 architect 先开始，调整列表顺序
swarm = Swarm([architect, researcher, coder, reviewer], ...)

# 如果想让 coder 先开始
swarm = Swarm([coder, researcher, architect, reviewer], ...)
```

> **注意**：官方文档提到了 `entry_point` 参数可以显式指定入口 Agent，但当前版本（2026年2月）尚未实现该参数，只能通过列表顺序控制入口。

### 2.3 关键配置参数

| 参数 | 作用 | 默认值 |
|------|------|--------|
| `max_handoffs` | 限制 Agent 间交接次数，防止无限循环 | 20 |
| `max_iterations` | 限制总迭代次数 | 20 |
| `execution_timeout` | 总执行超时（秒） | 900 |
| `node_timeout` | 单个 Agent 超时（秒） | 300 |
| `repetitive_handoff_detection_window` | 检测乒乓循环的窗口大小 | 0（禁用） |
| `repetitive_handoff_min_unique_agents` | 窗口内最少需要的不同 Agent 数量 | 0（禁用） |

> **返工场景配置建议**：如果启用返工机制，建议设置 `max_handoffs=15~20`，并启用乒乓检测防止无限循环：
> ```python
> swarm = Swarm(
>     [...],
>     max_handoffs=15,
>     repetitive_handoff_detection_window=6,  # 检查最近 6 次交接
>     repetitive_handoff_min_unique_agents=2   # 至少要有 2 个不同的 Agent
> )
> ```

---

## 3. handoff_to_agent 工具的实现

### 3.1 工具定义位置

`handoff_to_agent` 是 Swarm 框架内部定义的协调工具，**不需要用户手动创建**。它定义在 `strands/multiagent/swarm.py` 的 `_create_handoff_tool` 方法中：

```python
def _create_handoff_tool(self) -> Callable[..., Any]:
    """Create handoff tool for agent coordination."""
    swarm_ref = self  # Capture swarm reference

    @tool
    def handoff_to_agent(
        agent_name: str, 
        message: str, 
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Transfer control to another agent in the swarm for specialized help.

        Args:
            agent_name: Name of the agent to hand off to
            message: Message explaining what needs to be done and why you're handing off
            context: Additional context to share with the next agent

        Returns:
            Confirmation of handoff initiation
        """
        try:
            context = context or {}

            # Validate target agent exists
            target_node = swarm_ref.nodes.get(agent_name)
            if not target_node:
                return {
                    "status": "error", 
                    "content": [{"text": f"Error: Agent '{agent_name}' not found in swarm"}]
                }

            # Execute handoff - 这里触发共享知识的保存和上下文传递
            swarm_ref._handle_handoff(target_node, message, context)

            return {
                "status": "success", 
                "content": [{"text": f"Handed off to {agent_name}: {message}"}]
            }
        except Exception as e:
            return {"status": "error", "content": [{"text": f"Error in handoff: {str(e)}"}]}

    return handoff_to_agent
```

### 3.2 工具注入机制

Swarm 在初始化时，通过 `_inject_swarm_tools` 方法将 `handoff_to_agent` 工具自动注入到每个 Agent：

```python
def _inject_swarm_tools(self) -> None:
    """Add swarm coordination tools to each agent."""
    swarm_tools = [
        self._create_handoff_tool(),
    ]

    for node in self.nodes.values():
        # 将工具注册到每个 Agent 的工具列表中
        node.executor.tool_registry.process_tools(swarm_tools)
```

### 3.3 工具参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_name` | str | ✓ | 目标 Agent 的名称，必须是 Swarm 中存在的 Agent |
| `message` | str | ✓ | 交接说明，告诉下一个 Agent 需要做什么 |
| `context` | dict | ✗ | 共享知识，传递给下一个 Agent 的结构化数据 |

### 3.4 关键点

- **自动注入**：用户无需定义此工具，Swarm 框架自动处理
- **闭包引用**：工具内部持有 `swarm_ref` 引用，可以访问 Swarm 的状态和方法
- **验证机制**：调用时会验证目标 Agent 是否存在
- **状态更新**：通过 `_handle_handoff` 方法更新共享知识和当前执行节点

---

## 4. 任务上下文机制

### 4.1 上下文如何传递

当 Swarm 启动时，框架会自动为每个 Agent 注入 `handoff_to_agent` 工具，并构建完整的上下文信息。

每个 Agent 收到的上下文格式：

```
Handoff Message: The user needs help with Python debugging...

User Request: My Python script is throwing a KeyError

Previous agents who worked on this: data_analyst → code_reviewer

Shared knowledge from previous agents:
• data_analyst: {"issue_location": "line 42", "error_type": "missing key"}
• code_reviewer: {"code_quality": "good", "security_notes": "..."}

Other agents available for collaboration:
Agent name: data_analyst. Description: Analyzes data
Agent name: security_specialist. Description: Security expert
```

### 4.2 上下文包含的信息

| 信息类型 | 说明 |
|----------|------|
| 原始任务 | 用户最初提交的任务描述 |
| 交接消息 | 上一个 Agent 传递的具体说明 |
| 执行历史 | 哪些 Agent 已经处理过这个任务 |
| 共享知识 | 每个 Agent 贡献的工作成果 |
| 可用 Agent | 当前可以协作的其他 Agent 列表 |

---

## 5. 共享知识机制

### 5.1 工作原理

共享知识通过 `handoff_to_agent` 工具的 `context` 参数实现：

```python
# Agent 在交接时传递自己的工作成果
handoff_to_agent(
    agent_name="coder",
    message="I've completed the API design, please implement it",
    context={
        "endpoints": ["/api/v1/todos", "/api/v1/todos/{id}"],
        "data_model": {"id": "string", "title": "string", "completed": "boolean"},
        "best_practices": ["use proper HTTP methods", "implement pagination"]
    }
)
```

### 5.2 共享知识累积过程

```
researcher 完成调研
    │
    ├─→ context: {requirements: [...], best_practices: [...]}
    │
    ▼
architect 收到 researcher 的知识，完成设计
    │
    ├─→ context: {architecture: {...}, endpoints: [...]}
    │
    ▼
coder 收到 researcher + architect 的知识，完成编码
    │
    ├─→ context: {code: "...", implementation_notes: [...]}
    │
    ▼
reviewer 收到所有前序 Agent 的知识，完成审查
```

### 5.3 关键特性

- **累积性**：每个 Agent 的贡献都会被保留
- **可见性**：后续 Agent 可以看到所有前序 Agent 的工作成果
- **结构化**：通过 JSON 格式传递，便于解析和使用

---

## 6. 执行流程详解

### 6.1 触发与执行

```
swarm("Design a simple REST API for a todo app")
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Swarm 框架接收任务                              │
│  1. 找到第一个 Agent（researcher）               │
│  2. 组装 prompt：任务 + 上下文 + handoff 工具    │
│  3. 调用 researcher.invoke(prompt)              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  researcher Agent 工作                           │
│  - 分析任务，进行调研                            │
│  - 决定交接给 architect                          │
│  - 调用 handoff_to_agent("architect", ...)      │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Swarm 框架捕获 handoff                          │
│  1. 记录 researcher 的输出到共享知识             │
│  2. 更新上下文，组装新 prompt                    │
│  3. 调用 architect.invoke(新prompt)             │
└─────────────────────────────────────────────────┘
    │
    ▼
   ... 循环继续直到某个 Agent 不再 handoff ...
```

### 6.2 结束条件

Swarm 在以下情况结束执行：

1. 某个 Agent 完成任务后不再调用 `handoff_to_agent`
2. 达到 `max_handoffs` 限制
3. 达到 `max_iterations` 限制
4. 超过 `execution_timeout` 时间限制

---

## 7. 测试验证

### 7.1 测试代码

```python
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

# 配置模型
model = BedrockModel(
    model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-west-2"
)

# 创建 Agent
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

# 创建并执行 Swarm
swarm = Swarm(
    [researcher, architect, coder, reviewer],
    max_handoffs=10,
    max_iterations=15
)

result = swarm("Design a simple REST API for a todo app")
```

### 7.2 测试输出详解

#### 阶段一：Swarm 初始化

```
DEBUG | strands.multiagent.swarm | nodes=<['researcher', 'architect', 'coder', 'reviewer']> | initialized swarm with nodes
DEBUG | strands.multiagent.swarm | tool_count=<1>, node_count=<4> | injected coordination tools into agents
```

**日志解读：**
- `nodes=<['researcher', 'architect', 'coder', 'reviewer']>`：Swarm 识别到 4 个 Agent
- `tool_count=<1>`：为每个 Agent 注入了 1 个协调工具（`handoff_to_agent`）
- `node_count=<4>`：共 4 个节点参与协作

**这一步做了什么：** Swarm 框架遍历所有 Agent，给每个 Agent 的工具列表里自动添加 `handoff_to_agent` 工具，使它们具备交接能力。

---

#### 阶段二：启动执行

```
DEBUG | strands.multiagent.swarm | starting swarm execution
DEBUG | strands.multiagent.swarm | current_node=<researcher> | starting swarm execution with node
DEBUG | strands.multiagent.swarm | max_handoffs=<10>, max_iterations=<15>, timeout=<900.0>s | swarm execution config
```

**日志解读：**
- `current_node=<researcher>`：确认入口 Agent 是 researcher（列表第一个）
- `max_handoffs=<10>`：最多允许 10 次交接
- `max_iterations=<15>`：最多允许 15 次迭代
- `timeout=<900.0>s`：总超时 15 分钟

**这一步做了什么：** Swarm 确定入口 Agent，加载安全配置，准备开始执行。

---

#### 阶段三：researcher Agent 执行（迭代 1）

```
DEBUG | strands.multiagent.swarm | current_node=<researcher>, iteration=<1> | executing node
```

**日志解读：**
- `iteration=<1>`：这是第 1 次迭代
- `current_node=<researcher>`：当前执行的是 researcher

**researcher 收到的输入（由框架自动构建）：**
```
User Request: Design a simple REST API for a todo app

Other agents available for collaboration:
Agent name: architect.
Agent name: coder.
Agent name: reviewer.

You have access to swarm coordination tools if you need help from other agents.
If you don't hand off to another agent, the swarm will consider the task complete.
```

**researcher 的输出：**
```
I'll help gather requirements and research best practices for a todo app REST API...

Standard requirements for a todo app REST API typically include:
1. Core Functionality: Create, Read, Update, Delete todo items
2. Data Model Essential Fields: ID, Title, Completion status, Timestamps
3. Best Practices: Proper HTTP methods, RESTful naming, Pagination support
4. Common Endpoints: GET/POST/PUT/DELETE /todos

Now I'll hand off to the architect to design the API structure.
Tool #1: handoff_to_agent
```

**输出解读：**
- researcher 完成了需求调研，整理出 REST API 的核心功能、数据模型、最佳实践
- `Tool #1: handoff_to_agent`：researcher 决定调用 handoff 工具，把任务交给 architect
- **关键点**：这个交接决策是 researcher 自主做出的，不是外部强制的

---

#### 阶段四：交接到 architect（迭代 2）—— 共享上下文传递

```
DEBUG | strands.multiagent.swarm | from_node=<researcher>, to_node=<architect> | handed off from agent to agent
DEBUG | strands.multiagent.swarm | node=<researcher> | node execution completed
DEBUG | strands.multiagent.swarm | current_node=<architect>, iteration=<2> | executing node
```

**日志解读：**
- `from_node=<researcher>, to_node=<architect>`：交接发生，从 researcher 到 architect
- `node execution completed`：researcher 的工作结束
- `iteration=<2>`：进入第 2 次迭代

**🔑 共享上下文传递机制：**

当 researcher 调用 `handoff_to_agent("architect", message, context)` 时，Swarm 框架执行以下操作：

1. **保存交接消息**：`self.state.handoff_message = message`
2. **保存共享知识**：将 context 存入 `SharedContext` 对象
3. **构建新输入**：为 architect 构建包含完整上下文的输入

**architect 收到的输入（由框架自动构建）：**
```
Handoff Message: I've completed the requirements research. Please design the API architecture.

User Request: Design a simple REST API for a todo app

Previous agents who worked on this: researcher

Shared knowledge from previous agents:
• researcher: {"requirements": ["CRUD operations", "pagination"], "best_practices": ["RESTful naming", "proper HTTP methods"]}

Other agents available for collaboration:
Agent name: researcher.
Agent name: coder.
Agent name: reviewer.

You have access to swarm coordination tools if you need help from other agents.
```

**architect 的输出：**
```
I'll design the REST API architecture based on the research provided...

REST API Design for Todo App:
1. Base URL: /api/v1/todos
2. Endpoints:
   - GET /api/v1/todos (list with pagination)
   - GET /api/v1/todos/{id}
   - POST /api/v1/todos
   - PUT /api/v1/todos/{id}
   - DELETE /api/v1/todos/{id}
   - PATCH /api/v1/todos/{id}/toggle

Now I'll hand this off to the coder for implementation.
Tool #1: handoff_to_agent
```

**输出解读：**
- `based on the research provided`：证明 architect 收到了 researcher 的调研结果
- architect 设计了完整的 API 架构，包括 URL 结构和所有端点
- 再次调用 `handoff_to_agent` 交给 coder

---

#### 阶段五：交接到 coder（迭代 3）—— 共享内存累积

```
DEBUG | strands.multiagent.swarm | from_node=<architect>, to_node=<coder> | handed off from agent to agent
DEBUG | strands.multiagent.swarm | node=<architect> | node execution completed
DEBUG | strands.multiagent.swarm | current_node=<coder>, iteration=<3> | executing node
```

**🔑 共享知识累积机制：**

此时 `SharedContext` 中已累积了两个 Agent 的共享知识：

```python
shared_context = {
    "researcher": {
        "requirements": ["CRUD operations", "pagination", "error handling"],
        "best_practices": ["RESTful naming", "proper HTTP methods", "JSON format"]
    },
    "architect": {
        "base_url": "/api/v1/todos",
        "endpoints": ["GET /todos", "POST /todos", "PUT /todos/{id}", "DELETE /todos/{id}"],
        "data_model": {"id": "string", "title": "string", "completed": "boolean"}
    }
}
```

**coder 收到的输入：**
```
Handoff Message: API design is complete. Please implement the REST API.

User Request: Design a simple REST API for a todo app

Previous agents who worked on this: researcher → architect

Shared knowledge from previous agents:
• researcher: {"requirements": [...], "best_practices": [...]}
• architect: {"base_url": "/api/v1/todos", "endpoints": [...], "data_model": {...}}

Other agents available for collaboration:
Agent name: researcher.
Agent name: architect.
Agent name: reviewer.
```

**coder 的输出：**
```python
# 实现了完整的 FastAPI REST API 代码
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

app = FastAPI(title="Todo API", version="1.0.0")

# Data Model
class TodoBase(BaseModel):
    title: str

class Todo(TodoBase):
    id: str
    completed: bool
    created_at: datetime
    updated_at: datetime

# API Endpoints
@app.get("/api/v1/todos")
async def list_todos(...): ...

@app.post("/api/v1/todos", status_code=201)
async def create_todo(...): ...

@app.put("/api/v1/todos/{todo_id}")
async def update_todo(...): ...

@app.delete("/api/v1/todos/{todo_id}", status_code=204)
async def delete_todo(...): ...

@app.patch("/api/v1/todos/{todo_id}/toggle")
async def toggle_todo(...): ...

Let me hand this over to the reviewer for code review.
Tool #1: handoff_to_agent
```

**输出解读：**
- coder 实现的端点与 architect 设计的完全一致，证明上下文传递成功
- 使用 FastAPI 框架，包含数据模型、所有 CRUD 端点
- 继续交接给 reviewer 进行代码审查

---

#### 阶段六：交接到 reviewer（迭代 4）—— 完整上下文汇聚

```
DEBUG | strands.multiagent.swarm | from_node=<coder>, to_node=<reviewer> | handed off from agent to agent
DEBUG | strands.multiagent.swarm | node=<coder> | node execution completed
DEBUG | strands.multiagent.swarm | current_node=<reviewer>, iteration=<4> | executing node
```

**🔑 完整共享知识状态：**

此时 `SharedContext` 包含所有前序 Agent 的共享知识：

```python
shared_context = {
    "researcher": {
        "requirements": [...],
        "best_practices": [...]
    },
    "architect": {
        "base_url": "/api/v1/todos",
        "endpoints": [...],
        "data_model": {...}
    },
    "coder": {
        "framework": "FastAPI",
        "implementation_notes": ["Used Pydantic for validation", "In-memory storage"],
        "code_location": "main.py"
    }
}
```

**reviewer 收到的输入：**
```
Handoff Message: Implementation complete. Please review the code.

User Request: Design a simple REST API for a todo app

Previous agents who worked on this: researcher → architect → coder

Shared knowledge from previous agents:
• researcher: {"requirements": [...], "best_practices": [...]}
• architect: {"base_url": "/api/v1/todos", "endpoints": [...], "data_model": {...}}
• coder: {"framework": "FastAPI", "implementation_notes": [...]}

Other agents available for collaboration:
Agent name: researcher.
Agent name: architect.
Agent name: coder.
```

**reviewer 的输出：**
```
I'll review the implemented REST API based on the shared knowledge and requirements...

1. Architectural Design Compliance: ✓
   - Base URL structure (/api/v1/todos) is followed
   - All specified endpoints are implemented
   - HTTP methods are correctly mapped

2. Code Quality and Best Practices: ✓
   - Uses FastAPI framework
   - Includes input validation
   - Implements pagination

3. Error Handling: ✓
   - Proper HTTP status codes
   - Input validation errors handled

4. API Contract Adherence: ✓
   - All required endpoints present
   - Data model follows specification

5. Data Model Implementation: ✓
   - All required fields present
   - Correct data types

Overall Assessment: The implementation successfully meets all requirements.
No major issues found. Task completed.
```

**输出解读：**
- reviewer 能够对照 researcher 的需求、architect 的设计、coder 的代码进行全面审查
- 这证明了共享上下文机制工作正常——reviewer 看到了所有前序 Agent 的工作成果
- reviewer 没有调用 `handoff_to_agent`，表示任务完成

---

#### 阶段七：Swarm 结束

```
DEBUG | strands.multiagent.swarm | node=<reviewer> | no handoff occurred, marking swarm as complete
DEBUG | strands.multiagent.swarm | status=<Status.COMPLETED> | swarm execution completed
DEBUG | strands.multiagent.swarm | node_history_length=<4>, time=<73.67>s | metrics
```

**日志解读：**
- `no handoff occurred`：reviewer 没有调用 handoff，Swarm 判定任务完成
- `status=<Status.COMPLETED>`：最终状态为"已完成"
- `node_history_length=<4>`：共 4 个 Agent 参与
- `time=<73.67>s`：总耗时约 74 秒

**结束条件触发：** 当某个 Agent 完成工作后不再调用 `handoff_to_agent`，Swarm 认为任务已完成，结束执行。

---

#### 共享上下文与共享知识传递流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Swarm 执行流程                                     │
└─────────────────────────────────────────────────────────────────────────────┘

迭代 1: researcher
┌─────────────────────────────────────────────────────────────────────────────┐
│ 共享上下文（输入）:                                                          │
│   User Request: "Design a simple REST API for a todo app"                   │
│   Shared Knowledge: (空)                                                     │
│                                                                              │
│ 输出:                                                                        │
│   调研结果 + handoff_to_agent("architect", message, context={...})          │
│                                                     ↑                        │
│                                            这个 context 就是共享知识         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ context 存入 SharedContext（共享知识存储）
                                    
迭代 2: architect
┌─────────────────────────────────────────────────────────────────────────────┐
│ 共享上下文（输入）:                                                          │
│   Handoff Message: "..."                                                     │
│   User Request: "Design a simple REST API for a todo app"                   │
│   Previous agents: researcher                                                │
│   Shared Knowledge: {researcher: {...}}  ← 累积的共享知识                    │
│                                                                              │
│ 输出:                                                                        │
│   架构设计 + handoff_to_agent("coder", message, context={...})              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ context 追加到 SharedContext
                                    
迭代 3: coder
┌─────────────────────────────────────────────────────────────────────────────┐
│ 共享上下文（输入）:                                                          │
│   Handoff Message: "..."                                                     │
│   User Request: "Design a simple REST API for a todo app"                   │
│   Previous agents: researcher → architect                                    │
│   Shared Knowledge: {researcher: {...}, architect: {...}}  ← 累积           │
│                                                                              │
│ 输出:                                                                        │
│   代码实现 + handoff_to_agent("reviewer", message, context={...})           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ context 追加到 SharedContext
                                    
迭代 4: reviewer
┌─────────────────────────────────────────────────────────────────────────────┐
│ 共享上下文（输入）:                                                          │
│   Handoff Message: "..."                                                     │
│   User Request: "Design a simple REST API for a todo app"                   │
│   Previous agents: researcher → architect → coder                            │
│   Shared Knowledge: {researcher: {...}, architect: {...}, coder: {...}}     │
│                                                                              │
│ 输出:                                                                        │
│   代码审查结果（不调用 handoff，任务完成）                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

#### 完整执行时间线

```
时间线：
0s      ─────────────────────────────────────────────────────────────→ 73.67s

        │← researcher →│← architect →│←── coder ──→│←─ reviewer ─→│
        │   迭代 1     │   迭代 2    │    迭代 3    │    迭代 4    │
        │              │             │              │              │
        └── handoff ──→└── handoff ─→└── handoff ──→└── 完成 ─────→│
            + context     + context     + context
```

### 7.3 执行结果统计

```
==================================================
📊 执行结果概览
==================================================
状态: Status.COMPLETED
总执行时间: 73667ms
总迭代次数: 4

==================================================
🔄 Agent 执行顺序
==================================================
researcher → architect → coder → reviewer

==================================================
💰 Token 使用统计
==================================================
Input tokens: 9134
Output tokens: 3577
```

---

## 8. 测试分析

### 8.1 执行流程验证

| 验证项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| 入口 Agent | researcher 首先执行 | researcher 首先执行 | ✓ |
| 交接顺序 | researcher→architect→coder→reviewer | 完全一致 | ✓ |
| 自主决策 | 每个 Agent 自己决定交接 | 通过 handoff_to_agent 实现 | ✓ |
| 结束条件 | reviewer 不再交接时结束 | "no handoff occurred, marking swarm as complete" | ✓ |

### 8.2 上下文传递验证

从日志可以看到：

- **architect** 提到 "based on the research provided"，说明收到了 researcher 的调研结果
- **coder** 实现的 API 结构与 architect 设计完全一致，说明收到了架构设计
- **reviewer** 能够对照需求、架构、代码进行全面审查，说明收到了完整上下文

### 8.3 共享知识验证

每个 Agent 的工作成果被正确累积：

```
researcher: 需求调研 + 最佳实践
    ↓ 累积
architect: + API 架构设计
    ↓ 累积
coder: + 完整实现代码
    ↓ 累积
reviewer: 基于所有信息进行审查
```

### 8.4 安全机制验证

| 机制 | 配置 | 实际表现 |
|------|------|----------|
| max_handoffs=10 | 限制交接次数 | 实际交接 3 次，未触发限制 |
| max_iterations=15 | 限制迭代次数 | 实际迭代 4 次，未触发限制 |
| execution_timeout=900s | 总超时 | 实际 73.67s，未触发限制 |

---

## 9. 测试总结

### 9.1 Swarm 模式优势

1. **专业分工**：每个 Agent 专注自己的领域，提高输出质量
2. **自主协作**：无需预定义工作流，Agent 根据任务自动协调
3. **知识累积**：工作成果逐步累积，后续 Agent 可以利用前序成果
4. **灵活扩展**：可以轻松添加新的专业 Agent

### 9.2 适用场景

- 需要多专业领域协作的复杂任务（如：调研→设计→开发→审查）
- 任务流程不固定，需要根据情况动态调整
- 需要保留完整工作历史和决策过程

### 9.3 注意事项

1. **System Prompt 设计**：需要明确告诉 Agent 何时应该交接
2. **安全限制**：合理设置 max_handoffs 和 max_iterations 防止无限循环
3. **成本控制**：多 Agent 协作会消耗更多 Token，需要关注成本

### 9.4 与其他模式对比

| 模式 | 控制方式 | 适用场景 |
|------|----------|----------|
| Swarm | 去中心化，自主交接 | 复杂协作任务，流程不固定 |
| Orchestrator | 中央控制，统一调度 | 流程固定，需要严格控制 |
| Pipeline | 线性流水线 | 步骤固定的顺序任务 |

---

## 10. 返工机制测试

### 10.1 测试场景

为了验证 Swarm 的返工机制，我们设计了一个更复杂的任务，要求包含 JWT 认证、输入验证、安全配置等，更容易触发 reviewer 的返工要求。

### 10.2 测试配置

```python
# 关键：reviewer 可以将任务交回给前序 Agent
reviewer = Agent(
    name="reviewer",
    model=model,
    system_prompt="""You are a senior code reviewer.
    
    After review:
    - If you find CODE issues → Hand off to "coder" with specific issues
    - If you find ARCHITECTURE issues → Hand off to "architect"
    - If you find REQUIREMENT issues → Hand off to "researcher"
    - If everything looks good → Provide final approval WITHOUT handing off
    
    Be strict but fair."""
)

# 配置支持返工
swarm = Swarm(
    [researcher, architect, coder, reviewer],
    max_handoffs=15,
    max_iterations=20,
    repetitive_handoff_detection_window=6,
    repetitive_handoff_min_unique_agents=2
)
```

### 10.3 测试输出详解

#### 阶段一：Swarm 初始化

```
DEBUG | strands.multiagent.swarm | nodes=<['researcher', 'architect', 'coder', 'reviewer']> | initialized swarm with nodes
DEBUG | strands.multiagent.swarm | tool_count=<1>, node_count=<4> | injected coordination tools into agents
============================================================
🚀 Starting Swarm with Rework Mechanism
============================================================

Task: Design and implement a REST API for a todo app with the following requirements:
1. CRUD operations for todos
2. User authentication (JWT)
3. Input validation
4. Proper error responses with status codes
5. Pagination for list endpoints

DEBUG | strands.multiagent.swarm | starting swarm execution
DEBUG | strands.multiagent.swarm | current_node=<researcher> | starting swarm execution with node
DEBUG | strands.multiagent.swarm | max_handoffs=<15>, max_iterations=<20>, timeout=<900.0>s | swarm execution config
```

**日志解读：**
- 任务比简单测试更复杂，包含 JWT 认证、输入验证等安全要求
- `max_handoffs=<15>`：允许更多交接以支持返工
- `max_iterations=<20>`：允许更多迭代

---

#### 阶段二：正常流程（迭代 1-4）

```
DEBUG | strands.multiagent.swarm | current_node=<researcher>, iteration=<1> | executing node
... researcher 完成需求调研 ...
DEBUG | strands.multiagent.swarm | from_node=<researcher>, to_node=<architect> | handed off

DEBUG | strands.multiagent.swarm | current_node=<architect>, iteration=<2> | executing node
... architect 完成架构设计 ...
DEBUG | strands.multiagent.swarm | from_node=<architect>, to_node=<coder> | handed off

DEBUG | strands.multiagent.swarm | current_node=<coder>, iteration=<3> | executing node
... coder 完成初版实现 ...
DEBUG | strands.multiagent.swarm | from_node=<coder>, to_node=<reviewer> | handed off

DEBUG | strands.multiagent.swarm | current_node=<reviewer>, iteration=<4> | executing node
```

**reviewer 第一次审查发现问题：**
```
I notice some potential security concerns that need to be addressed:
1. Missing rate limiting for authentication endpoints
2. No specification of JWT expiration and refresh mechanism
3. No CORS policy defined
4. No input sanitization mentioned beyond validation

Given these security concerns, I'll hand off to the coder to implement these security improvements:
Tool #1: handoff_to_agent
```

---

#### 阶段三：第一次返工（迭代 5）

```
DEBUG | strands.multiagent.swarm | from_node=<reviewer>, to_node=<coder> | handed off from agent to agent
DEBUG | strands.multiagent.swarm | node=<reviewer> | node execution completed
DEBUG | strands.multiagent.swarm | current_node=<coder>, iteration=<5> | executing node
```

**🔑 返工触发：** reviewer 发现安全问题，将任务交回给 coder

**coder 收到的反馈：**
```
Handoff Message: Please implement these security enhancements:
- Rate limiting (5 req/min for auth, 100 req/min for API)
- JWT token expiration (15m access, 7d refresh)
- CORS configuration
- Input sanitization using xss package
```

**coder 修复后再次提交：**
```
This implementation includes all the requested security enhancements...
Let me hand this off to the reviewer for final verification:
Tool #2: handoff_to_agent
```

---

#### 阶段四：第二次审查（迭代 6）

```
DEBUG | strands.multiagent.swarm | from_node=<coder>, to_node=<reviewer> | handed off
DEBUG | strands.multiagent.swarm | current_node=<reviewer>, iteration=<6> | executing node
```

**reviewer 要求进一步验证：**
```
I need to verify specific security implementation details:
- Rate limiting exact values
- JWT token expiry settings
- Password hashing configuration
- CORS implementation

I'll hand off to the coder for specific implementation verifications:
Tool #2: handoff_to_agent
```

---

#### 阶段五：第二次返工（迭代 7）

```
DEBUG | strands.multiagent.swarm | from_node=<reviewer>, to_node=<coder> | handed off
DEBUG | strands.multiagent.swarm | current_node=<coder>, iteration=<7> | executing node
```

**coder 提供详细配置验证：**
```python
# config/config.ts - 明确的安全配置
export const config = {
  jwt: {
    accessTokenExpiry: '15m',    // 15分钟
    refreshTokenExpiry: '7d'     // 7天
  }
};

// middleware/rateLimiter.ts
export const authRateLimiter = rateLimit({
  windowMs: 60 * 1000,  // 1分钟
  max: 5                // 5次请求
});

// bcrypt 配置
const BCRYPT_ROUNDS = 10;  // 行业标准
```

---

#### 阶段六：最终审批（迭代 8）

```
DEBUG | strands.multiagent.swarm | from_node=<coder>, to_node=<reviewer> | handed off
DEBUG | strands.multiagent.swarm | current_node=<reviewer>, iteration=<8> | executing node
```

**reviewer 最终审批：**
```
Security Analysis:
1. Rate Limiting: ✓ Properly implemented
2. JWT Implementation: ✓ Well configured
3. Password Security: ✓ Meets standards (bcrypt with 10 rounds)
4. CORS: ✓ Securely configured
5. Input Validation: ✓ Comprehensive

The implementation is APPROVED for production use.
```

---

#### 阶段七：Swarm 结束

```
DEBUG | strands.multiagent.swarm | node=<reviewer> | no handoff occurred, marking swarm as complete
DEBUG | strands.multiagent.swarm | status=<Status.COMPLETED> | swarm execution completed
DEBUG | strands.multiagent.swarm | node_history_length=<8>, time=<258.43>s | metrics
```

**日志解读：**
- `no handoff occurred`：reviewer 最终批准，不再交接
- `node_history_length=<8>`：共 8 次迭代（比简单测试的 4 次多一倍）
- `time=<258.43>s`：总耗时约 4.3 分钟

### 10.4 测试结果统计

```
==================================================
🔄 Agent 执行顺序（含返工）
==================================================
researcher → architect → coder → reviewer → coder → reviewer → coder → reviewer

各 Agent 调用次数:
  researcher: 1 次
  architect: 1 次
  coder: 3 次 (有返工)
  reviewer: 3 次 (有返工)

==================================================
📊 执行结果概览
==================================================
状态: Status.COMPLETED
总执行时间: 258430ms（约 4.3 分钟）
总迭代次数: 8

==================================================
💰 Token 使用统计
==================================================
Input tokens: 59580
Output tokens: 23827
```

### 10.4 测试结果统计

```
==================================================
🔄 Agent 执行顺序（含返工）
==================================================
researcher → architect → coder → reviewer → coder → reviewer → coder → reviewer

各 Agent 调用次数:
  researcher: 1 次
  architect: 1 次
  coder: 3 次 (有返工)
  reviewer: 3 次 (有返工)

==================================================
📊 执行结果概览
==================================================
状态: Status.COMPLETED
总执行时间: 258430ms（约 4.3 分钟）
总迭代次数: 8

==================================================
💰 Token 使用统计
==================================================
Input tokens: 59580
Output tokens: 23827
```

### 10.5 返工流程分析

```
迭代 1-4: 正常流程
researcher → architect → coder → reviewer
                                    │
                                    ▼ reviewer 发现安全问题
迭代 5: 第一次返工               
reviewer → coder（要求添加 rate limiting、JWT expiry 等）
                │
                ▼
迭代 6: coder 修复后再次提交
coder → reviewer
            │
            ▼ reviewer 要求验证具体配置
迭代 7: 第二次返工
reviewer → coder（要求确认安全配置细节）
                │
                ▼
迭代 8: 最终审批
coder → reviewer → 完成（所有安全要求满足）
```

### 10.6 返工触发的问题

reviewer 在第一次审查时发现的问题：

1. **缺少 rate limiting**：认证端点需要限流防止暴力破解
2. **JWT 过期机制不明确**：需要明确 access token 和 refresh token 的过期时间
3. **CORS 配置缺失**：需要配置跨域策略
4. **输入消毒不完整**：需要 XSS 防护

### 10.7 返工机制验证

| 验证项 | 结果 |
|--------|------|
| reviewer 能否交回给 coder | ✓ 成功触发 2 次 |
| coder 能否接收反馈并修复 | ✓ 每次都针对性修复 |
| 共享知识是否正确累积 | ✓ 包含所有迭代的上下文 |
| 乒乓检测是否工作 | ✓ 未触发（有足够的不同 Agent） |
| 最终能否正常结束 | ✓ reviewer 最终批准 |

### 10.8 返工 vs 无返工对比

| 指标 | 无返工（简单任务） | 有返工（复杂任务） |
|------|-------------------|-------------------|
| 迭代次数 | 4 | 8 |
| 执行时间 | 73.67s | 258.43s |
| Input Tokens | 9,134 | 59,580 |
| Output Tokens | 3,577 | 23,827 |
| 代码质量 | 基础实现 | 生产级安全配置 |

### 10.9 返工机制总结

1. **返工是 Swarm 的核心能力**：支持任意方向的交接，不仅是线性流程
2. **System Prompt 是关键**：需要明确告诉 Agent 在什么情况下返工
3. **安全配置很重要**：启用乒乓检测防止无限循环
4. **成本会增加**：返工会显著增加 Token 消耗，需要权衡质量和成本

---

## 11. 参考资料

- [Strands Agents 官方文档](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/)
- [Strands Agents GitHub](https://github.com/strands-agents/strands-agents)

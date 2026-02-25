# Swarm Multi-Agent with Strands Agents SDK

基于 [Strands Agents SDK](https://strandsagents.com/) 的 Swarm 多智能体协作示例。

## 什么是 Swarm

Swarm 是一种去中心化的多智能体协作模式，多个专业化 Agent 通过自主交接完成复杂任务，无需中央调度器。

```
Agent A ←→ Agent B
   ↖    ↗
    Agent C
```

## 快速开始

### 安装依赖

```bash
pip install strands-agents strands-agents-tools
```

### 配置 AWS 凭证

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-west-2
```

### 运行示例

```bash
python swarm_demo.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `swarm_demo.py` | 可运行的 Swarm 示例代码 |
| `Swarm_Multi_Agent_Guide.md` | 详细的机制解析文档 |

## 示例输出

```
🔄 Agent 执行顺序
researcher → architect → coder → reviewer

📊 执行结果概览
状态: Status.COMPLETED
总执行时间: 73667ms
总迭代次数: 4
```

## 核心概念

- **共享上下文**：每个 Agent 都能看到完整的任务背景和执行历史
- **共享知识**：Agent 通过 `handoff_to_agent` 的 `context` 参数传递工作成果
- **自主交接**：Agent 自己决定何时把任务交给谁

详细说明请参考 [Swarm_Multi_Agent_Guide.md](./Swarm_Multi_Agent_Guide.md)

## 参考资料

- [Strands Agents 官方文档](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/)
- [Strands Agents GitHub](https://github.com/strands-agents/strands-agents)

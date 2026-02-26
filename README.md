# Swarm Multi-Agent with Strands Agents SDK

基于 [Strands Agents SDK](https://strandsagents.com/) 的 Swarm 多智能体协作示例。

## 什么是 Swarm

Swarm 是一种去中心化的多智能体协作模式，多个专业化 Agent 通过自主交接完成复杂任务，无需中央调度器。

```
正常流程：
researcher → architect → coder → reviewer → 完成

返工流程（支持任意方向交接）：
researcher → architect → coder → reviewer → coder → reviewer → 完成
                                    ↑          ↓
                                    └── 返工 ───┘
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
# 基础示例（线性流程）
python swarm_demo.py

# 返工机制示例（支持 reviewer 将任务交回修改）
python swarm_demo_with_rework.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `swarm_demo.py` | 基础 Swarm 示例（线性流程） |
| `swarm_demo_with_rework.py` | 支持返工的 Swarm 示例 |
| `Swarm_Multi_Agent_Guide.md` | 详细的机制解析文档 |

## 示例输出

### 基础示例
```
🔄 Agent 执行顺序
researcher → architect → coder → reviewer

📊 执行结果概览
状态: Status.COMPLETED
总执行时间: 73667ms
总迭代次数: 4
```

### 返工示例
```
🔄 Agent 执行顺序（含返工）
researcher → architect → coder → reviewer → coder → reviewer → coder → reviewer

各 Agent 调用次数:
  researcher: 1 次
  architect: 1 次
  coder: 3 次 (有返工)
  reviewer: 3 次 (有返工)

📊 执行结果概览
状态: Status.COMPLETED
总执行时间: 258430ms
总迭代次数: 8
```

## 核心概念

- **共享上下文**：每个 Agent 都能看到完整的任务背景和执行历史
- **共享知识**：Agent 通过 `handoff_to_agent` 的 `context` 参数传递工作成果
- **自主交接**：Agent 自己决定何时把任务交给谁
- **返工机制**：支持任意方向的交接，reviewer 可以将任务交回给前序 Agent 修改

详细说明请参考 [Swarm_Multi_Agent_Guide.md](./Swarm_Multi_Agent_Guide.md)

## 参考资料

- [Strands Agents 官方文档](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/)
- [Strands Agents GitHub](https://github.com/strands-agents/strands-agents)

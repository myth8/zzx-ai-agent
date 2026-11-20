可以。先建立一个核心认识：**`MultiStepAgent` 主要负责管理“多步运行”，而每一步具体怎么调用模型、执行动作，由子类实现。**

因此，第一阶段建议你把阅读重点放在：

1. `run()`：一次任务怎样开始、怎样返回。
2. `_run_stream()`：循环怎样推进、什么时候停止。
3. `_step_stream()`：父类定义接口，子类实现一次具体行动。
4. 错误处理和达到最大步数后的兜底逻辑。

下面的行号基于当前工作区的代码：[agents.py (line 268)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:268)。

------

## 一、先看整体调用链

从外部调用 `agent.run("任务")` 开始，核心路径可以简化成：

```
agent.run(task)
│
├─ 准备任务、状态、记忆等
│
└─ _run_stream(task, max_steps)
   │
   ├─ 初始化 step_number = 1
   │
   ├─ while 没有最终答案 且 未超过最大步数
   │  │
   │  ├─ 如果到了规划时机：生成 PlanningStep
   │  │
   │  ├─ 创建 ActionStep
   │  │
   │  ├─ 调用子类的 _step_stream(action_step)
   │  │  ├─ 读取之前的记忆，组织模型输入
   │  │  ├─ 调用模型
   │  │  ├─ 解析并执行模型给出的动作
   │  │  └─ 产出 ActionOutput
   │  │
   │  ├─ 如果 ActionOutput 是最终答案：检查并结束循环
   │  └─ 记录本步、调用回调、步数加一
   │
   ├─ 如果达到最大步数：请求模型给一个兜底答案
   └─ 产出 FinalAnswerStep
```

你可以把它看成两层：

- **外层循环**：`MultiStepAgent._run_stream()` 决定何时执行下一步、何时停止。
- **内层单步**：`ToolCallingAgent` 或 `CodeAgent` 的 `_step_stream()` 决定一步内部如何思考和行动。

------

## 二、类定义：它是一个抽象基类

从 [agents.py (line 268)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:268) 开始：

```
class MultiStepAgent(ABC):
```

这里继承 `ABC`，说明它被设计为其他 Agent 的基础类。类注释在第 270～271 行说明了它采用的 ReAct 思路：模型产生动作，环境返回观察，循环直到任务完成。

这句话对应的代码结构就是：

```
模型输出动作 → 执行动作 → 记录观察 → 下一轮模型调用
```

但要注意，**`MultiStepAgent` 本身没有实现具体的单步动作**。第 772 行的 `_step_stream()` 直接抛出 `NotImplementedError`；真正的实现分别在：

- [ToolCallingAgent._step_stream (line 1276)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1276)
- [CodeAgent._step_stream (line 1638)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1638)

### 先记住这几个对象

| 对象               | 在 Agent Loop 中的作用                         |
| ------------------ | ---------------------------------------------- |
| `self.model`       | 根据输入生成下一步行动                         |
| `self.memory`      | 保存任务、行动、观察等历史                     |
| `self.tools`       | 可供行动使用的工具集合                         |
| `self.step_number` | 当前行动步数                                   |
| `ActionStep`       | 一次行动的记录                                 |
| `ActionOutput`     | 单步执行完成时产出的结果，并标记是否为最终答案 |
| `FinalAnswerStep`  | 整次运行最后产出的答案事件                     |

目前只需要知道这些对象在循环中的作用；具体的数据结构可以后续按你的学习顺序展开。

------

## 三、初始化：`__init__`

从 [agents.py (line 294)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:294) 开始。

初始化不是循环本身，但它准备了循环运行所需的对象。

### 1. 保存模型与提示词配置

从 [agents.py (line 313)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:313) 开始：

```
self.agent_name = self.__class__.__name__
self.model = model
self.prompt_templates = prompt_templates or EMPTY_PROMPT_TEMPLATES
```

- `self.model` 保存模型对象。
- `self.prompt_templates` 保存系统提示词、规划提示词等模板。
- 后面的第 316～326 行会检查自定义模板是否缺少必要的键。

这里值得注意：父类不直接写死一个模型，也不写死某一种单步执行方式。模型与具体 Agent 类型都是可替换的。

### 2. 初始化循环控制状态

从 [agents.py (line 328)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:328) 开始：

```
self.max_steps = max_steps
self.step_number = 0
self.planning_interval = planning_interval
self.state: dict[str, Any] = {}
```

这几个字段直接影响运行：

- `max_steps`：允许执行的最大**行动步数**。
- `step_number`：当前步数；正式进入 `_run_stream()` 时会重置为 1。
- `planning_interval`：是否以及多频繁地插入规划步骤。
- `state`：保存额外变量和部分运行状态。

`max_steps` 约束的是外层循环中的行动步；规划步骤是插在行动步之前的，不会单独让 `step_number` 加一。

### 3. 准备工具、托管 Agent 与记忆

从 [agents.py (line 338)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:338) 开始：

```
self._setup_managed_agents(managed_agents)
self._setup_tools(tools, add_base_tools)
self._validate_tools_and_managed_agents(tools, managed_agents)

self.task: str | None = None
self.memory = AgentMemory(self.system_prompt)
```

当前阶段关注两点即可：

1. 工具和托管 Agent 在运行前被整理到 Agent 上。
2. `memory` 在实例化时创建，后续任务、行动和观察会被加入其中。

[agents.py (line 402)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:402) 还会默认加入 `final_answer` 工具。在工具调用模式中，模型可以通过它表达“我已经有最终答案”。

### 4. 日志和回调

从 [agents.py (line 345)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:345) 开始创建 logger、monitor 和回调注册表。

这里先只记住：**每一步结束时会触发回调**。日志、指标和具体遥测的实现可以留到最后的 Telemetry 阶段。

------

## 四、运行入口：`run()`

从 [agents.py (line 436)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:436) 开始。

`run()` 是使用者最常接触的入口。它负责准备一次运行，并根据 `stream` 决定如何向调用方返回结果。

### 1. 确定本次任务与最大步数

从 [agents.py (line 468)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:468) 开始：

```
max_steps = max_steps or self.max_steps
self.task = task
self.interrupt_switch = False
```

执行顺序是：

1. 优先使用本次传入的 `max_steps`，否则使用初始化时的值。
2. 把当前任务保存到 `self.task`。
3. 清除中断标记，为新的一次运行做准备。

这里使用的是 `or`，所以传入 `0` 也会回退到 `self.max_steps`。

### 2. 处理额外参数

从 [agents.py (line 471)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:471) 开始：

```
if additional_args:
    self.state.update(additional_args)
    self.task += ...
```

传入的额外参数会被放进 `self.state`，同时任务文本会追加一段说明，告诉 Agent 可以通过变量名访问这些参数。

暂时可以理解成：除了用户的自然语言任务，运行时还可以提供一些可供行动使用的对象。

### 3. 更新系统提示词，按需重置记忆

从 [agents.py (line 477)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:477) 开始：

```
self.memory.system_prompt = SystemPromptStep(system_prompt=self.system_prompt)
if reset:
    self.memory.reset()
    self.monitor.reset()
```

- 每次运行都会重新生成并设置系统提示词。
- 默认 `reset=True`，会重置之前的步骤记忆及监控数据。
- `reset=False` 时，先前步骤会保留，可以接着已有历史运行。

注意：这里的 `reset` 并不是对 Agent 实例所有属性做全面重建；例如本段代码没有清空 `self.state`。

### 4. 把当前任务写入记忆

从 [agents.py (line 482)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:482) 开始记录任务，关键行是：

```
self.memory.steps.append(TaskStep(task=self.task, task_images=images))
```

之后子类执行每一步时，会从记忆构造模型输入。也就是说，任务进入模型输入的路径大致是：

```
run(task)
  → 创建 TaskStep
  → 加入 memory.steps
  → 单步执行时转成模型消息
```

### 5. 为代码执行环境准备变量与工具

从 [agents.py (line 490)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:490) 开始：

```
if getattr(self, "python_executor", None):
    self.python_executor.send_variables(variables=self.state)
    self.python_executor.send_tools({**self.tools, **self.managed_agents})
```

如果当前 Agent 有 Python 执行器，就把状态变量和可用工具发给它。

这主要是 `CodeAgent` 单步执行代码所需的准备。执行器本身可以等学习 Tool Calling 时再深入。

### 6. 流式与非流式返回

从 [agents.py (line 494)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:494) 开始：

```
if stream:
    return self._run_stream(...)

steps = list(self._run_stream(...))
```

两条分支使用的是同一个 `_run_stream()`：

- `stream=True`：返回生成器，由调用方迭代；**只有开始迭代，生成器内部的循环才会执行**。
- `stream=False`：用 `list(...)` 在内部把生成器完整跑完，再取最终结果。

还有一个容易混淆的配置：`stream_outputs` 控制模型生成内容是否按增量输出；它与 `run(stream=True)` 是否向调用方返回步骤生成器是两个不同层次的设置。

### 7. 整理返回值

从 [agents.py (line 501)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:501) 开始：

```
assert isinstance(steps[-1], FinalAnswerStep)
output = steps[-1].output
```

非流式运行依赖一个约定：`_run_stream()` 正常结束时，最后产出的事件是 `FinalAnswerStep`。

如果 `return_full_result=True`，第 505～536 行还会汇总 token、步骤、耗时和状态，返回 `RunResult`；否则第 538 行直接返回答案。

------

## 五、核心循环：`_run_stream()`

这是第一阶段最值得反复阅读的方法：[agents.py (line 540)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:540)。

### 1. 循环的两个退出条件

从 [agents.py (line 543)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:543) 开始：

```
self.step_number = 1
returned_final_answer = False

while not returned_final_answer and self.step_number <= max_steps:
    ...
```

一开始：

- 行动步数从 1 开始。
- 还没有拿到已接受的最终答案。

循环持续的前提是同时满足：

1. 尚未接受最终答案。
2. 当前步数没有超过上限。

这就是 Agent Loop 的骨架。之后所有规划、模型调用、动作执行和错误处理都发生在这个循环里。

### 2. 检查外部中断

从 [agents.py (line 546)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:546) 开始：

```
if self.interrupt_switch:
    raise AgentError("Agent interrupted.", self.logger)
```

对应的 `interrupt()` 在 [agents.py (line 754)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:754)，只负责把标记设置为 `True`。

因此，中断检查发生在**每次进入下一轮循环时**；它不是直接在任意位置强制终止正在执行的模型调用或工具。

### 3. 可选规划步骤

从 [agents.py (line 549)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:549) 开始：

```
if self.planning_interval is not None and (
    self.step_number == 1
    or (self.step_number - 1) % self.planning_interval == 0
):
```

如果启用了规划：

- 第 1 步行动前会规划。
- 之后按照 `planning_interval` 再次规划。

例如 `planning_interval=3` 时，规划发生在行动步 1、4、7……之前。

第 555 行调用 `_generate_planning_step()`，消费并转发它产出的事件；最终得到 `PlanningStep`，记录结束时间、触发回调，并加入记忆。

这里有一个观察生成器顺序的细节：第 558 行先 `yield element`，恢复执行后才给 `planning_step` 赋值；而规划步骤是在循环结束后才被 finalize 并写入记忆。因此，消费流时看到某个事件，不代表后续所有收尾操作已经完成。

### 4. 为本轮创建 `ActionStep`

从 [agents.py (line 569)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:569) 开始：

```
action_step = ActionStep(
    step_number=self.step_number,
    timing=Timing(start_time=action_step_start_time),
    observations_images=images,
)
```

`ActionStep` 是**本轮的记录容器**。父类先创建它，然后传给子类。子类在执行过程中把模型输入、模型输出、动作、观察等信息填进去。

可以将其理解成：

```
父类创建空的本轮记录
    ↓
子类执行本轮，并填写记录
    ↓
父类完成收尾并保存记录
```

### 5. 执行子类的单步逻辑

从 [agents.py (line 577)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:577) 开始：

```
for output in self._step_stream(action_step):
    yield output
    ...
```

这是父类和子类之间最关键的边界：

- 父类负责循环。
- `self._step_stream(...)` 会根据实际 Agent 类型，调用子类实现。
- 子类执行过程中产出的事件，会被父类继续 `yield` 给外部。

例如：

```
CodeAgent.run()
  → MultiStepAgent._run_stream()
  → CodeAgent._step_stream()
```

虽然 `run()` 和 `_run_stream()` 定义在父类中，但 `self` 仍然是实际的 `CodeAgent` 实例，所以会进入子类的 `_step_stream()`。

### 6. 判断是否产生最终答案

从 [agents.py (line 582)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:582) 开始：

```
if isinstance(output, ActionOutput) and output.is_final_answer:
    final_answer = output.output

    if self.final_answer_checks:
        self._validate_final_answer(final_answer)

    returned_final_answer = True
    action_step.is_final_answer = True
```

父类并不通过“输出内容看起来像答案”来猜测，而是检查子类产出的 `ActionOutput.is_final_answer`。

如果配置了 `final_answer_checks`，会先验证答案；验证通过后才把 `returned_final_answer` 设为 `True`，从而在本轮结束后退出 `while`。

**注意事件顺序：**第 580 行先把 `output` yield 出去，随后才在第 582 行判断并执行最终答案检查。所以流式调用方可能先看到一个标记为最终答案的 `ActionOutput`，而验证要在生成器继续运行时才进行。最终是否完成应以之后的流程为准。

### 7. 错误处理与本轮收尾

从 [agents.py (line 594)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:594) 开始：

```
except AgentGenerationError as e:
    raise e
except AgentError as e:
    action_step.error = e
finally:
    self._finalize_step(action_step)
    self.memory.steps.append(action_step)
    yield action_step
    self.step_number += 1
```

按代码行为区分：

- `AgentGenerationError`：重新抛出，运行退出。
- 其他被捕获的 `AgentError`：记录到当前 `ActionStep.error`；如果没有其他异常阻止，循环可继续下一步。
- `finally`：收尾当前步骤，包括设置结束时间、触发回调、加入记忆，并产出该 `ActionStep`。

因为下一轮会读取已有记忆，记录下来的错误可以成为后续模型输入的一部分，让模型有机会调整行动。记忆具体如何转换为消息，可以留到 Context 阶段看。

还有一个生成器细节：`yield action_step` 在 `step_number += 1` 之前，因此调用方收到这个事件时，生成器尚未执行步数加一；再次迭代时才会继续。

### 8. 达到最大步数后的兜底

从 [agents.py (line 606)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:606) 开始：

```
if not returned_final_answer and self.step_number == max_steps + 1:
    final_answer = self._handle_max_steps_reached(task)
    yield action_step
```

如果行动次数耗尽仍没有最终答案：

1. 调用 `_handle_max_steps_reached(task)`。
2. 该方法会额外请求模型根据已有过程给出一个答案。
3. 最后统一封装为 `FinalAnswerStep`。

这里需要区分：`max_steps` 限制循环中的行动步；触顶后仍可能进行一次用于生成兜底答案的模型调用。

------

## 六、为什么 `_step_stream()` 要由子类实现？

父类接口在 [agents.py (line 772)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:772)：

```
def _step_stream(self, memory_step: ActionStep):
    raise NotImplementedError(...)
```

父类知道“一步应该发生在循环里”，但不限定模型如何表达动作。两个主要子类实现了不同的单步方式。

### 1. `ToolCallingAgent`：模型输出工具调用

入口：[agents.py (line 1276)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1276)。

你可以先按以下节点跳读：

| 位置                                                         | 这一块做什么                                  |
| ------------------------------------------------------------ | --------------------------------------------- |
| [1284 行 (line 1284)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1284) | 把已有记忆转换为模型输入消息                  |
| [1291 行 (line 1291)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1291) | 调用模型，获取本轮输出                        |
| [1320 行 (line 1320)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1320) | 将模型输出写入当前 `ActionStep`               |
| [1327 行 (line 1327)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1327) | 解析或整理工具调用                            |
| [1336 行 (line 1336)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1336) | 处理工具调用并产出事件                        |
| [1356 行 (line 1356)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1356) | 产出 `ActionOutput`，告诉外层是否得到最终答案 |

当前只需理解其形状：

```
历史消息
  → 模型产生工具调用
  → 执行工具并得到结果
  → 产出 ActionOutput
  → 父类决定继续还是结束
```

工具的参数解析、执行和并行处理，适合放在你的下一阶段 Tool Calling 中详细看。

### 2. `CodeAgent`：模型输出代码

入口：[agents.py (line 1638)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1638)。

| 位置                                                         | 这一块做什么                     |
| ------------------------------------------------------------ | -------------------------------- |
| [1646 行 (line 1646)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1646) | 构造模型输入                     |
| [1655 行 (line 1655)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1655) | 调用模型生成内容                 |
| [1702 行 (line 1702)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1702) | 从模型输出中解析代码             |
| [1715 行 (line 1715)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1715) | 将代码执行表示为 `ToolCall` 事件 |
| [1723 行 (line 1723)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1723) | 通过 Python 执行器执行代码       |
| [1752 行 (line 1752)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1752) | 记录执行观察                     |
| [1764 行 (line 1764)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1764) | 产出 `ActionOutput`              |

它的形状是：

```
历史消息
  → 模型生成代码
  → 解析并执行代码
  → 记录执行结果
  → 产出 ActionOutput
  → 父类决定继续还是结束
```

这也解释了为什么外层循环可以共用：**无论动作是工具调用还是代码执行，子类最终都用 `ActionOutput` 向父类报告结果。**

------

## 七、与循环直接相关的辅助方法

### `write_memory_to_messages()`：为下一步提供历史

位置：[agents.py (line 758)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:758)。

```
messages = self.memory.system_prompt.to_messages(summary_mode=summary_mode)
for memory_step in self.memory.steps:
    messages.extend(memory_step.to_messages(summary_mode=summary_mode))
return messages
```

它把系统提示词和各个记忆步骤转换成模型消息。两种子类的 `_step_stream()` 都会先调用它。

在 Agent Loop 阶段，只要把它当成一个接口：

```
已记录的任务、行动、观察等 → 下一次模型调用的输入
```

至于各种 `MemoryStep` 如何编码、`summary_mode` 如何影响消息，留到 Context 阶段更合适。

### `_validate_final_answer()`：检查答案能否被接受

位置：[agents.py (line 613)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:613)。

它依次调用 `final_answer_checks` 中的函数，传入答案、记忆和 Agent。如果检查失败或抛出异常，会包装为 `AgentError`。

在外层循环里，这种错误会记入当前 `ActionStep`。由于设置 `returned_final_answer = True` 的代码还没执行，循环可以继续，让 Agent 再尝试。

### `_finalize_step()`：统一收尾

位置：[agents.py (line 620)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:620)。

对于非最终答案步骤，它设置结束时间；然后触发对应的回调。

这就是 Agent Loop 与 Telemetry 的一个连接点，目前知道“步骤完成后会通知回调”即可。

### `_handle_max_steps_reached()`：触顶后的处理

位置：[agents.py (line 625)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:625)。

它调用 [provide_final_answer() (line 810)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:810)，根据历史构造提示词，再请求模型生成兜底答案；随后创建一个带有 `AgentMaxStepsError` 的 `ActionStep` 并加入记忆。

`provide_final_answer()` 内部如果模型调用抛出异常，会返回一个包含错误说明的 `ChatMessage`。因此，兜底路径并不保证任务一定解决，它只保证尝试产出可返回的内容。

------

## 八、用一个例子串起来

假设：

```
agent.run("查找某项数据并计算结果", max_steps=3)
```

忽略规划步骤，可能发生下面的过程：

```
run()
  保存任务
  任务写入 memory
  消费 _run_stream()

第 1 步
  创建 ActionStep 1
  子类读取 memory，调用模型
  模型提出动作
  执行动作，得到观察
  ActionOutput.is_final_answer = False
  保存 ActionStep 1

第 2 步
  创建 ActionStep 2
  子类读取任务和第 1 步记录，调用模型
  模型根据观察继续行动
  ActionOutput.is_final_answer = False
  保存 ActionStep 2

第 3 步
  创建 ActionStep 3
  子类再次读取历史，调用模型
  模型给出最终答案
  ActionOutput.is_final_answer = True
  可选的最终答案检查通过
  保存 ActionStep 3

退出循环
  产出 FinalAnswerStep
  run() 返回答案
```

如果第 3 步结束仍没有被接受的最终答案，则走最大步数兜底路径。

------

## 九、建议你第一次按这个顺序读

为了避免同时掉进所有模块，建议先打开 [agents.py (line 268)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:268)，按以下路线跳读：

1. **[436 行 `run()` (line 436)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:436)**：看任务如何进入，结果如何返回。
2. **[540 行 `_run_stream()` (line 540)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:540)**：重点看 `while`、调用 `_step_stream()`、判断最终答案、异常处理。
3. **[772 行父类 `_step_stream()` (line 772)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:772)**：理解为什么它只是子类接口。
4. 二选一浏览单步实现：想先看工具调用就看 [ToolCallingAgent (line 1276)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1276)；想先看模型写代码就看 [CodeAgent (line 1638)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:1638)。第一遍只找“模型输入 → 模型输出 → 执行动作 → `ActionOutput`”。
5. 最后回看 [294 行 `__init__()` (line 294)](/Users/zhuzhuoxuan/zhuzhuoxuan/zzx-env/opencode/smolagents/src/smolagents/agents.py:294)，把循环中用到的成员与初始化参数对应起来。

第一遍读完，可以用一个问题检验是否掌握：**“上一轮观察是怎样影响下一轮的，最终答案又是在哪一层决定停止循环的？”** 前者经过 `ActionStep → memory → 模型消息`，后者由子类标记 `ActionOutput`，再由父类 `_run_stream()` 检查并结束循环。
// Single source of truth for engine metadata shared by the hub, session list
// and chat pages. `chatType` is what the backend persists in sessions.chat_type.
export const ENGINES = {
  react: {
    key: 'react',
    chatType: 'agent',
    path: '/super-agent/react',
    label: 'LangChain ReAct',
    shortLabel: 'ReAct',
    badge: 'BASELINE',
    eyebrow: 'TEXT REACT · LANGCHAIN',
    headline: '成熟稳定的基线引擎',
    description: '经典 ReAct 文本推理循环，由 LangChain AgentExecutor 驱动，适合日常问答与稳定生产链路。',
    actionLanguage: 'Thought / Action / Observation 文本',
    accent: '#67e8f9',
    themeClass: 'theme-react',
    features: ['LangChain AgentExecutor', '文本式工具调用', '成熟、可预测', '与既有会话完全兼容'],
    bestFor: '通用问答、稳定优先的线上任务',
    icon: 'M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5l2.6-1.5M17.2 9l2.6-1.5M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z'
  },
  toolcalling: {
    key: 'toolcalling',
    chatType: 'toolcalling',
    path: '/super-agent/toolcalling',
    label: 'MultiStep · ToolCallingAgent',
    shortLabel: 'Tool Calling',
    badge: 'STRUCTURED',
    eyebrow: 'NATIVE FUNCTION CALLING',
    headline: '结构化工具调用引擎',
    description: '手写 MultiStepAgent 负责多步循环，模型通过原生 function calling 返回结构化工具参数，适合与 LangChain 做同条件性能对比。',
    actionLanguage: 'JSON Tool Calls',
    accent: '#a78bfa',
    themeClass: 'theme-toolcalling',
    features: ['原生 function calling', '复用同一套工具', '参数校验更直接', '适合工具链基准测试'],
    bestFor: '多工具任务、结构化参数、性能对比',
    icon: 'M14.5 4.5 19 9l-9.5 9.5H5v-4.5L14.5 4.5ZM12 7l5 5M4 20h16'
  },
  code: {
    key: 'code',
    chatType: 'code',
    path: '/super-agent/code',
    label: 'MultiStep · CodeAgent',
    shortLabel: 'Code Agent',
    badge: 'CODE',
    eyebrow: 'PYTHON AS ACTION LANGUAGE',
    headline: '用 Python 思考与行动',
    description: '模型把一小段 Python 作为动作语言，在一次动作里循环、组合工具、保存变量并计算中间结果，适合复杂编排与数据处理。',
    actionLanguage: 'Python Code',
    accent: '#34d399',
    themeClass: 'theme-code',
    features: ['Python 作为动作语言', '一次动作编排多个工具', '变量跨步持久化', '受限 AST 解释器执行'],
    bestFor: '数据分析、多步计算、复杂工具编排',
    icon: 'M8 5 3 12l5 7M16 5l5 7-5 7M13.5 4l-3 16'
  }
}

export const ENGINE_LIST = [ENGINES.react, ENGINES.toolcalling, ENGINES.code]
export const DEFAULT_ENGINE = 'react'

export function resolveEngine(key) {
  return ENGINES[key] || ENGINES[DEFAULT_ENGINE]
}

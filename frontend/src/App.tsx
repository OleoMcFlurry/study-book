import {
  Alert,
  Block,
  Button,
  Checkbox,
  Empty,
  Flexbox,
  Input,
  InputNumber,
  InputPassword,
  Select,
  Tag,
  Text,
  TextArea,
  ThemeSwitch,
  type ThemeSwitchProps,
} from "@lobehub/ui";
import {
  BookOpen,
  BrainCircuit,
  GitBranch,
  Route,
  Save,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const LLM_STORAGE_KEY = "knowledge_path_demo_llm_v1";

const LEVELS = [
  { label: "不了解", value: "unknown" },
  { label: "了解", value: "heard" },
  { label: "掌握", value: "understood" },
  { label: "熟练掌握", value: "proficient" },
  { label: "精通", value: "expert" },
] as const;

type LlmConfig = {
  api_key: string;
  base_url: string;
  enable_thinking: boolean;
  max_tokens: number | null;
  model: string;
  reasoning_effort: "none" | "low" | "medium" | "high";
  temperature: number | null;
};

type GraphNode = { description: string; id: string; title: string };
type GraphEdge = { from: string; to: string };
type PathItem = {
  acceptance_question: string;
  actions: string[];
  node_id: string;
  title: string;
};
type StudySession = {
  background: string;
  gaps: string[];
  goal: string;
  graph: { edges: GraphEdge[]; nodes: GraphNode[] } | null;
  mastery: Record<string, string>;
  path: PathItem[] | null;
  session_id: string;
  status: string;
};

const INITIAL_LLM: LlmConfig = {
  api_key: "",
  base_url: "",
  enable_thinking: false,
  max_tokens: null,
  model: "",
  reasoning_effort: "none",
  temperature: 0.2,
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw data.detail ?? data;
  return data as T;
}

function formatError(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return JSON.stringify(error, null, 2);
}

type AppProps = {
  onThemeSwitch: ThemeSwitchProps["onThemeSwitch"];
  themeMode: ThemeSwitchProps["themeMode"];
};

export default function App({ onThemeSwitch, themeMode }: AppProps) {
  const [llm, setLlm] = useState<LlmConfig>(INITIAL_LLM);
  const [serverHint, setServerHint] = useState("正在读取服务端配置…");
  const [goal, setGoal] = useState("");
  const [background, setBackground] = useState("");
  const [keywords, setKeywords] = useState("");
  const [session, setSession] = useState<StudySession | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<"create" | "graph" | "path" | "">("");
  const gaps = useMemo(() => new Set(session?.gaps ?? []), [session?.gaps]);

  useEffect(() => {
    const stored = localStorage.getItem(LLM_STORAGE_KEY);
    let hasStoredConfig = false;
    if (stored) {
      try {
        setLlm({ ...INITIAL_LLM, ...JSON.parse(stored) });
        hasStoredConfig = true;
      } catch {
        localStorage.removeItem(LLM_STORAGE_KEY);
      }
    }

    api<{
      base_url: string;
      enable_thinking: boolean;
      has_server_api_key: boolean;
      max_tokens: number | null;
      model: string;
      reasoning_effort: LlmConfig["reasoning_effort"];
    }>("/api/llm/defaults")
      .then((defaults) => {
        setLlm((current) => ({
          ...current,
          base_url: current.base_url || defaults.base_url,
          enable_thinking: hasStoredConfig
            ? current.enable_thinking
            : defaults.enable_thinking,
          max_tokens: current.max_tokens ?? defaults.max_tokens,
          model: current.model || defaults.model,
          reasoning_effort: hasStoredConfig
            ? current.reasoning_effort
            : defaults.reasoning_effort,
        }));
        setServerHint(
          defaults.has_server_api_key
            ? "服务端已配置默认密钥；API Key 留空时使用服务端配置。"
            : "服务端未配置密钥；生成内容前需填写 API Key。"
        );
      })
      .catch(() => setServerHint("无法读取服务端默认配置。"));
  }, []);

  const llmBody = () => {
    const override: Record<string, unknown> = {
      base_url: llm.base_url || undefined,
      enable_thinking: llm.enable_thinking,
      model: llm.model || undefined,
      reasoning_effort: llm.reasoning_effort,
      temperature: llm.temperature,
    };
    if (llm.api_key) override.api_key = llm.api_key;
    if (llm.max_tokens && llm.max_tokens > 0)
      override.max_tokens = llm.max_tokens;
    return { llm: override };
  };

  const saveLlm = () => {
    localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(llm));
    setServerHint("模型配置已保存到本机浏览器。");
    setError("");
  };

  const createSession = async () => {
    setError("");
    setLoading("create");
    try {
      const value = await api<StudySession>("/api/sessions", {
        body: JSON.stringify({
          background: background.trim(),
          goal: goal.trim(),
          known_keywords: keywords
            .split(/[,，]/)
            .map((item) => item.trim())
            .filter(Boolean),
        }),
        method: "POST",
      });
      setSession(value);
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setLoading("");
    }
  };

  const generateGraph = async () => {
    if (!session) return;
    setError("");
    setLoading("graph");
    try {
      setSession(
        await api<StudySession>(`/api/sessions/${session.session_id}/graph`, {
          body: JSON.stringify(llmBody()),
          method: "POST",
        })
      );
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setLoading("");
    }
  };

  const updateMastery = async (nodeId: string, level: string) => {
    if (!session) return;
    setError("");
    try {
      setSession(
        await api<StudySession>(`/api/sessions/${session.session_id}/mastery`, {
          body: JSON.stringify({ level, node_id: nodeId }),
          method: "PUT",
        })
      );
    } catch (reason) {
      setError(formatError(reason));
    }
  };

  const generatePath = async () => {
    if (!session) return;
    setError("");
    setLoading("path");
    try {
      setSession(
        await api<StudySession>(`/api/sessions/${session.session_id}/path`, {
          body: JSON.stringify(llmBody()),
          method: "POST",
        })
      );
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setLoading("");
    }
  };

  return (
    <div className="app-shell" data-theme={themeMode}>
      <header className="hero">
        <Flexbox align="center" horizontal justify="space-between">
          <Flexbox gap={8}>
            <Flexbox align="center" gap={10} horizontal>
              <div className="hero-icon">
                <BookOpen size={24} />
              </div>
              <Text as="h1" className="hero-title">
                知识路径学习
              </Text>
            </Flexbox>
            <Text className="hero-subtitle">
              从目标出发，识别知识依赖，标记掌握程度，生成专属补缺路径。
            </Text>
          </Flexbox>
          <ThemeSwitch onThemeSwitch={onThemeSwitch} themeMode={themeMode} />
        </Flexbox>
      </header>

      <main className="page-grid">
        <Flexbox gap={16}>
          <Section icon={<BrainCircuit size={19} />} step="01" title="模型配置">
            <div className="form-grid two-columns">
              <Field label="API Key">
                <InputPassword
                  autoComplete="off"
                  onChange={(event) =>
                    setLlm({ ...llm, api_key: event.target.value })
                  }
                  placeholder="sk-... 或网关密钥"
                  value={llm.api_key}
                />
              </Field>
              <Field label="Base URL">
                <Input
                  onChange={(event) =>
                    setLlm({ ...llm, base_url: event.target.value })
                  }
                  placeholder="https://api.openai.com/v1"
                  value={llm.base_url}
                />
              </Field>
              <Field label="模型名称">
                <Input
                  onChange={(event) =>
                    setLlm({ ...llm, model: event.target.value })
                  }
                  placeholder="gpt-4o-mini"
                  value={llm.model}
                />
              </Field>
              <Field label="思考强度">
                <Select
                  onChange={(value) =>
                    setLlm({ ...llm, reasoning_effort: value })
                  }
                  options={[
                    { label: "关闭", value: "none" },
                    { label: "低", value: "low" },
                    { label: "中", value: "medium" },
                    { label: "高", value: "high" },
                  ]}
                  value={llm.reasoning_effort}
                />
              </Field>
              <Field label="输出 Token 上限">
                <InputNumber
                  min={1}
                  onChange={(value) =>
                    setLlm({ ...llm, max_tokens: value ? Number(value) : null })
                  }
                  placeholder="留空表示不发送限制字段"
                  style={{ width: "100%" }}
                  value={llm.max_tokens ?? undefined}
                />
              </Field>
              <Field label="Temperature">
                <InputNumber
                  max={2}
                  min={0}
                  onChange={(value) =>
                    setLlm({
                      ...llm,
                      temperature: value == null ? null : Number(value),
                    })
                  }
                  step={0.1}
                  style={{ width: "100%" }}
                  value={llm.temperature ?? undefined}
                />
              </Field>
            </div>
            <Flexbox
              align="center"
              className="section-footer"
              horizontal
              justify="space-between"
            >
              <Checkbox
                checked={llm.enable_thinking}
                onChange={(checked) =>
                  setLlm({ ...llm, enable_thinking: checked })
                }
              >
                发送 enable_thinking
              </Checkbox>
              <Button icon={Save} onClick={saveLlm} type="primary">
                保存到本机
              </Button>
            </Flexbox>
            <Text className="helper-text">{serverHint}</Text>
          </Section>

          <Section icon={<Sparkles size={19} />} step="02" title="定义学习目标">
            <Flexbox gap={14}>
              <Field label="学习目标">
                <TextArea
                  autoSize={{ maxRows: 5, minRows: 2 }}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder="例如：掌握机器学习中的 Transformer 架构"
                  value={goal}
                />
              </Field>
              <Field label="背景与能力">
                <TextArea
                  autoSize={{ maxRows: 5, minRows: 2 }}
                  onChange={(event) => setBackground(event.target.value)}
                  placeholder="相关经验、学习用途与时间预算"
                  value={background}
                />
              </Field>
              <Field label="已知关键词">
                <Input
                  onChange={(event) => setKeywords(event.target.value)}
                  placeholder="以逗号分隔，例如：Python，线性代数"
                  value={keywords}
                />
              </Field>
              <Button
                block
                disabled={!goal.trim()}
                icon={Sparkles}
                loading={loading === "create"}
                onClick={createSession}
                size="large"
                type="primary"
              >
                创建学习会话
              </Button>
            </Flexbox>
          </Section>
        </Flexbox>

        <Flexbox gap={16}>
          <Section
            icon={<GitBranch size={19} />}
            step="03"
            title="知识依赖与掌握度"
          >
            <Flexbox
              align="center"
              className="session-bar"
              horizontal
              justify="space-between"
            >
              <Flexbox gap={4}>
                <Text className="helper-text">当前会话</Text>
                <Text code>{session?.session_id ?? "尚未创建"}</Text>
              </Flexbox>
              <Tag color={session ? "blue" : undefined}>
                {session?.status ?? "等待开始"}
              </Tag>
            </Flexbox>
            <Button
              block
              disabled={!session}
              icon={GitBranch}
              loading={loading === "graph"}
              onClick={generateGraph}
            >
              生成依赖图
            </Button>

            <Flexbox className="node-list" gap={10}>
              {!session?.graph?.nodes.length ? (
                <Empty description="生成依赖图后，在此逐项标记掌握程度" />
              ) : (
                session.graph.nodes.map((node, index) => (
                  <Block
                    className="knowledge-node"
                    key={node.id}
                    padding={14}
                    variant="outlined"
                  >
                    <Flexbox align="flex-start" gap={12} horizontal>
                      <div className="node-index">
                        {String(index + 1).padStart(2, "0")}
                      </div>
                      <Flexbox flex={1} gap={6}>
                        <Flexbox
                          align="center"
                          horizontal
                          justify="space-between"
                        >
                          <Text strong>{node.title}</Text>
                          {gaps.has(node.id) && (
                            <Tag color="orange">知识缺口</Tag>
                          )}
                        </Flexbox>
                        <Text className="node-description">
                          {node.description || "暂无说明"}
                        </Text>
                        <Select
                          onChange={(value) => updateMastery(node.id, value)}
                          options={LEVELS.map((item) => ({ ...item }))}
                          value={session.mastery[node.id] ?? "unknown"}
                        />
                      </Flexbox>
                    </Flexbox>
                  </Block>
                ))
              )}
            </Flexbox>
          </Section>

          <Section icon={<Route size={19} />} step="04" title="补缺学习路径">
            <Button
              block
              disabled={!session?.graph}
              icon={Route}
              loading={loading === "path"}
              onClick={generatePath}
              type="primary"
            >
              生成补缺路径
            </Button>
            <Flexbox className="path-list" gap={12}>
              {!session?.path?.length ? (
                <Empty description="完成掌握度标记后生成学习路径" />
              ) : (
                session.path.map((item, index) => (
                  <Block
                    className="path-item"
                    key={item.node_id}
                    padding={16}
                    variant="outlined"
                  >
                    <Flexbox gap={10}>
                      <Flexbox align="center" gap={10} horizontal>
                        <div className="path-index">{index + 1}</div>
                        <Text strong>{item.title}</Text>
                      </Flexbox>
                      <ul>
                        {item.actions.map((action) => (
                          <li key={action}>{action}</li>
                        ))}
                      </ul>
                      <Block
                        className="acceptance"
                        padding={10}
                        variant="filled"
                      >
                        <Text className="helper-text">验收问题</Text>
                        <Text>{item.acceptance_question}</Text>
                      </Block>
                    </Flexbox>
                  </Block>
                ))
              )}
            </Flexbox>
          </Section>
        </Flexbox>
      </main>

      {error && (
        <div className="error-dock">
          <Alert
            closable
            description={<pre>{error}</pre>}
            message="请求失败"
            onClose={() => setError("")}
            type="error"
          />
        </div>
      )}
    </div>
  );
}

function Field({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <label className="field">
      <Text className="field-label" strong>
        {label}
      </Text>
      {children}
    </label>
  );
}

function Section({
  children,
  icon,
  step,
  title,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  step: string;
  title: string;
}) {
  return (
    <Block className="section-card" padding={18} shadow variant="outlined">
      <Flexbox gap={16}>
        <Flexbox align="center" horizontal justify="space-between">
          <Flexbox align="center" gap={9} horizontal>
            <div className="section-icon">{icon}</div>
            <Text as="h2" className="section-title">
              {title}
            </Text>
          </Flexbox>
          <Text className="step-label">STEP {step}</Text>
        </Flexbox>
        {children}
      </Flexbox>
    </Block>
  );
}

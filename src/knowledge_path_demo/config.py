"""应用配置。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务端默认 LLM 与数据库配置；可被界面请求覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    database_path: str = "data/sessions.db"
    # 默认思考强度：none|low|medium|high
    llm_reasoning_effort: str = "none"
    # 默认输出 token 上限；0 表示不发送
    llm_max_tokens: int = 0
    llm_enable_thinking: bool = False
    # 依赖图约束
    graph_max_nodes: int = 80
    graph_max_depth: int = 24

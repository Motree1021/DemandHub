import os

import pytest

from app.agent.llm_client import ArkClient
from app.config import get_settings


@pytest.fixture
async def real_ark():
    if not os.getenv("LLM_API_KEY", "").strip():
        pytest.skip("未配置真实LLM_API_KEY，模型评测待外部验收")
    client = ArkClient(get_settings())
    yield client
    await client.close()

import os

from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI

# from langchain_wenxin import ChatWenxin
from langchain_community.chat_models import QianfanChatEndpoint, ChatZhipuAI

from config_manager import ConfigManager

_ = load_dotenv(find_dotenv())
cfg = ConfigManager()


def load_llm(model: str = None, temperature: float = None, json_mode=False):
    model = cfg.DEFAULT_MODEL if model is None else model
    temperature = temperature if temperature else cfg.DEFAULT_TMP
    if model in cfg.QIANFAN_MODELS:
        temperature = temperature if temperature else cfg.QIANFAN_DEF_TMP
        if json_mode:
            return QianfanChatEndpoint(
                streaming=True,
                model=model,
                temperature=temperature,
                model_kwargs={"response_format": "json_object"},
            )
        else:
            return QianfanChatEndpoint(
                streaming=True, model=model, temperature=temperature
            )
    elif model in cfg.ZHIPU_MODELS:
        temperature = temperature if temperature else cfg.ZHIPU_DEF_TMP
        if json_mode:
            raise Exception("ZhipuAI does not currently support JSON mode")
        else:
            return ChatZhipuAI(
                streaming=True,
                model=model,
                temperature=temperature,
                api_key=os.getenv("BIGMODEL_API_KEY"),
            )
    elif model in cfg.OPENAI_MODELS:
        temperature = temperature if temperature else cfg.OPENAI_DEF_TMP
        if json_mode:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                organization=cfg.OPENAI_ORG,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        else:
            return ChatOpenAI(
                model=model, temperature=temperature, organization=cfg.OPENAI_ORG
            )
    elif model in cfg.DEEPSEEK_MODELS:
        temperature = temperature if temperature else cfg.DEEPSEEK_DEF_TMP
        if json_mode:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                organization=cfg.OPENAI_ORG,
                model_kwargs={"response_format": {"type": "json_object"}},
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com"),
            )
        else:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                organization=cfg.OPENAI_ORG,
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com"),
            )
    elif model in cfg.BAILIAN_MODELS:
        temperature = temperature if temperature else cfg.BAILIAN_DEF_TMP
        if json_mode:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                organization=cfg.OPENAI_ORG,
                model_kwargs={"response_format": {"type": "json_object"}},
                api_key=os.getenv("QWEN_API_KEY"),
                base_url=os.getenv("QWEN_API_URL"),
            )
        else:
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                organization=cfg.OPENAI_ORG,
                api_key=os.getenv("QWEN_API_KEY"),
                base_url=os.getenv("QWEN_API_URL"),
            )

    else:
        raise Exception("Model name error (not supported)")


def get_default_temperature(model: str):
    if model in cfg.QIANFAN_MODELS:
        return cfg.QIANFAN_DEF_TMP
    elif model in cfg.ZHIPU_MODELS:
        return cfg.ZHIPU_DEF_TMP
    elif model in cfg.OPENAI_MODELS:
        return cfg.OPENAI_DEF_TMP
    elif model in cfg.DEEPSEEK_MODELS:
        return cfg.DEEPSEEK_DEF_TMP
    elif model in cfg.BAILIAN_MODELS:
        return cfg.BAILIAN_DEF_TMP
    else:
        raise Exception("Model name error (not supported)")

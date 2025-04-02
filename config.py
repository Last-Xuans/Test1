import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# API配置
LLM_API_CONFIG = {
    # 默认使用通义千问API
    "API_URL": os.getenv("LLM_API_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"),
    "API_KEY": os.getenv("LLM_API_KEY", ""),
    "MODEL": os.getenv("LLM_MODEL", "qwen-max"),
    "TEMPERATURE": 0.1,  # 低温度确保回答更确定性
    "MAX_TOKENS": 1000,
}

# Google搜索API配置
GOOGLE_SEARCH_CONFIG = {
    "ENABLED": os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true",
    "API_KEY": os.getenv("GOOGLE_API_KEY", ""),
    "SEARCH_ENGINE_ID": os.getenv("GOOGLE_SEARCH_ENGINE_ID", ""),
    "MAX_RESULTS": 5,
    "DAILY_LIMIT": 100  # 每日查询限额
}

# 检测阈值配置
THRESHOLDS = {
    "EMOTION_WORDS_RATIO": 0.15,  # 情绪词比例阈值
    "GRAMMAR_ERROR_RATIO": 0.05,  # 语法错误率阈值
    "HIGH_RISK_THRESHOLD": 70,    # 高风险阈值
    "LOW_RISK_THRESHOLD": 30      # 低风险阈值
}

# Web应用配置
WEB_CONFIG = {
    "TITLE": "虚假新闻检测系统",
    "DESCRIPTION": "基于规则与大模型的虚假新闻检测工具",
    "THEME": "soft",
    "PORT": 7860
}

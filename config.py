"""
系统配置文件
"""
import os
from pathlib import Path

# 项目路径
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

# 确保目录存在
RESULTS_DIR.mkdir(exist_ok=True)

# API配置
API_URLS = {
    "llm": "https://api.modelarts-maas.com/v2/chat/completions",
    "embed": "https://api.modelarts-maas.com/v1/embeddings",
    "rerank": "https://api.modelarts-maas.com/v1/rerank"
}

# 模型配置
PRIMARY_MODELS = [
    "deepseek-v3.2",
    "glm-5",
    "qwen3-235b-a22b",
]

SECONDARY_MODELS = [
    "deepseek-v4-pro",
    "kimi-k2.6",
]

ALL_MODELS = PRIMARY_MODELS + SECONDARY_MODELS

# 检索参数
DEFAULT_TOP_K = 10
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
REQUEST_TIMEOUT = 15

# ICD知识库路径
ICD_LIB_PATH = DATA_DIR / "icd10_data" / "ICD-10医保1.0版.总表.三位码.别名.csv"
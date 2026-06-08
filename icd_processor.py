"""
ICD编码处理器 - 从你的原始代码改造而来
"""
import pandas as pd
import numpy as np
import requests
import json
import re
import time
import warnings
import urllib3
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from config import (
    API_URLS, ALL_MODELS, PRIMARY_MODELS, SECONDARY_MODELS,
    DEFAULT_TOP_K, DEFAULT_CONFIDENCE_THRESHOLD, REQUEST_TIMEOUT,
    ICD_LIB_PATH
)
from utils.api_client import APIClient
from utils.logger import setup_logger

# 抑制警告
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = setup_logger()

class ICDProcessor:
    """ICD编码处理器"""
    
    def __init__(self, api_key: str, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD, 
                 top_k: int = DEFAULT_TOP_K):
        self.api_key = api_key
        self.confidence_threshold = confidence_threshold
        self.top_k = top_k
        self.api_client = APIClient(api_key)
        
        # ICD知识库
        self.icd_df = None
        self.icd_vectors = None
        self.icd_texts = []
        self.icd_codes = []
        self.icd_names = []
        self.code_to_name = {}
        self.name_to_code = {}
        
        # 模型管理
        self.current_model = PRIMARY_MODELS[0]
        self.model_stats = {model: {'success': 0, 'fail': 0, 'times': []} 
                           for model in ALL_MODELS}
        
    def load_knowledge_base(self, icd_path: str = None) -> bool:
        """加载ICD知识库并构建向量索引"""
        try:
            path = icd_path or ICD_LIB_PATH
            
            # 检查文件是否存在
            if not Path(path).exists():
                logger.error(f"ICD知识库文件不存在: {path}")
                return False
            
            # 加载数据
            self.icd_df = pd.read_csv(path)
            
            # 构建检索文本
            self.icd_df['检索文本'] = self.icd_df.apply(
                lambda row: f"{row['三位名称']}；别名：{row['别名']}" 
                if pd.notna(row.get('别名')) and row.get('别名') 
                else row['三位名称'],
                axis=1
            )
            
            self.icd_texts = self.icd_df['检索文本'].tolist()
            self.icd_codes = self.icd_df['三位码'].tolist()
            self.icd_names = self.icd_df['三位名称'].tolist()
            self.code_to_name = dict(zip(self.icd_codes, self.icd_names))
            self.name_to_code = dict(zip(self.icd_names, self.icd_codes))
            
            # 构建向量索引
            logger.info(f"开始向量化 {len(self.icd_texts)} 条ICD记录...")
            self.icd_vectors = self._build_vectors(self.icd_texts)
            
            logger.info(f"✅ ICD知识库加载成功: {len(self.icd_texts)} 条记录")
            return True
            
        except Exception as e:
            logger.error(f"❌ ICD知识库加载失败: {str(e)}")
            return False
    
    def _build_vectors(self, texts: List[str]) -> np.ndarray:
        """构建向量索引"""
        vectors = []
        batch_size = 100
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            try:
                embeddings = self.api_client.get_embeddings(batch)
                vectors.extend(embeddings)
            except Exception as e:
                logger.error(f"向量化批次 {i//batch_size} 失败: {str(e)}")
                vectors.extend([[0]*1024] * len(batch))
        
        return np.array(vectors)
    
    def process_single(self, diagnosis: str, index: int) -> Dict:
        """处理单条诊断"""
        result = {
            '序号': index,
            '原始诊断': diagnosis,
            'Step1': {},
            'Step2': {},
            'Step3': {},
            '最终ICD编码': '',
            '最终置信度': 0,
            '匹配方式': '',
            '处理状态': '失败',
            '处理时间': 0
        }
        
        start_time = time.time()
        
        if pd.isna(diagnosis) or diagnosis == "":
            result['处理状态'] = '空诊断'
            result['处理时间'] = time.time() - start_time
            return result
        
        # Step 1: LLM归一化
        step1_result = self._step1_normalize(diagnosis, index)
        result['Step1'] = step1_result
        
        if step1_result['状态'] != '成功':
            result['处理状态'] = f"Step1失败: {step1_result.get('错误信息', '')}"
            result['处理时间'] = time.time() - start_time
            return result
        
        # 处理非肿瘤
        extracted_term = step1_result.get('提取的术语', '')
        if extracted_term == "非肿瘤诊断" or (not step1_result.get('提取的编码') and not extracted_term):
            result['处理状态'] = '非肿瘤诊断或无法识别'
            result['处理时间'] = time.time() - start_time
            return result
        
        # 尝试直接编码
        direct_code = step1_result.get('提取的编码', '')
        if direct_code and direct_code in self.code_to_name:
            result['最终ICD编码'] = direct_code
            result['最终置信度'] = 0.99
            result['匹配方式'] = '直接编码'
            result['处理状态'] = '成功'
            result['Step2'] = {'状态': '跳过（直接编码匹配）'}
            result['Step3'] = {'状态': '跳过（直接编码匹配）'}
            result['处理时间'] = time.time() - start_time
            return result
        
        # Step 2: 向量检索
        search_term = extracted_term if extracted_term else diagnosis
        step2_result, candidates = self._step2_retrieve(search_term)
        result['Step2'] = step2_result
        
        if step2_result['状态'] != '成功' or not candidates:
            result['处理状态'] = f"Step2失败: {step2_result.get('错误信息', '无候选')}"
            result['处理时间'] = time.time() - start_time
            return result
        
        # Step 3: 精排
        step3_result, best_match, score = self._step3_rerank(search_term, candidates)
        result['Step3'] = step3_result
        
        if best_match and score >= self.confidence_threshold:
            result['最终ICD编码'] = best_match['ICD编码']
            result['最终置信度'] = score
            result['匹配方式'] = '检索匹配'
            result['处理状态'] = '成功'
        elif best_match:
            result['最终ICD编码'] = ''
            result['最终置信度'] = score
            result['匹配方式'] = '检索匹配(低置信度)'
            result['处理状态'] = f'低于置信度阈值({self.confidence_threshold})'
        else:
            result['处理状态'] = 'Step3未找到匹配'
        
        result['处理时间'] = time.time() - start_time
        return result
    
    def _step1_normalize(self, diagnosis: str, index: int) -> Dict:
        """Step 1: LLM提取编码"""
        # 这里整合你的step1_normalize逻辑
        # 使用self.api_client.call_llm_with_rotation()
        # 返回标准化的结果字典
        pass
    
    def _step2_retrieve(self, query: str) -> Tuple[Dict, List]:
        """Step 2: 向量检索"""
        # 整合你的step2_retrieve逻辑
        pass
    
    def _step3_rerank(self, query: str, candidates: List) -> Tuple[Dict, Dict, float]:
        """Step 3: 精排"""
        # 整合你的step3_rerank逻辑
        pass
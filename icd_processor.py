"""
ICD编码处理器 - 完整的核心处理逻辑
"""
import pandas as pd
import numpy as np
import requests
import json
import re
import time
import warnings
import urllib3
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from itertools import cycle

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

logger = setup_logger('processor')

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
        self.request_counter = 0
        
    def load_knowledge_base(self, icd_path: str = None) -> bool:
        """加载ICD知识库并构建向量索引"""
        try:
            path = icd_path or ICD_LIB_PATH
            
            # 检查文件是否存在
            if not Path(path).exists():
                logger.error(f"ICD知识库文件不存在: {path}")
                return False
            
            logger.info(f"正在加载ICD知识库: {path}")
            
            # 加载数据
            self.icd_df = pd.read_csv(path)
            logger.info(f"ICD知识库加载完成，共 {len(self.icd_df)} 条记录")
            
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
            
            # 建立映射
            self.code_to_name = dict(zip(self.icd_codes, self.icd_names))
            self.name_to_code = dict(zip(self.icd_names, self.icd_codes))
            
            # 构建向量索引
            logger.info(f"开始构建向量索引，共 {len(self.icd_texts)} 条记录...")
            self.icd_vectors = self._build_vectors(self.icd_texts)
            
            if self.icd_vectors is None or len(self.icd_vectors) == 0:
                logger.error("向量索引构建失败")
                return False
            
            logger.info(f"✅ ICD知识库加载成功: {len(self.icd_texts)} 条记录, 向量维度: {self.icd_vectors.shape}")
            return True
            
        except Exception as e:
            logger.error(f"❌ ICD知识库加载失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _build_vectors(self, texts: List[str]) -> np.ndarray:
        """构建向量索引"""
        vectors = []
        batch_size = 100
        success_count = 0
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            try:
                embeddings = self.api_client.get_embeddings(batch)
                vectors.extend(embeddings)
                success_count += len(batch)
                logger.info(f"向量化进度: {min(i+batch_size, len(texts))}/{len(texts)}")
            except Exception as e:
                logger.error(f"向量化批次 {i//batch_size + 1} 失败: {str(e)}")
                # 用零向量填充失败的批次
                vectors.extend([[0.0]*1024] * len(batch))
        
        logger.info(f"向量化完成: {success_count}/{len(texts)} 条成功")
        return np.array(vectors) if vectors else None
    
    def process_single(self, diagnosis: str, index: int) -> Dict:
        """处理单条诊断记录"""
        process_start_time = time.time()
        
        result = {
            '序号': index,
            '原始诊断': diagnosis,
            'Step1': {},
            'Step2': {},
            'Step3': {},
            '最终ICD编码': '',
            '最终置信度': 0.0,
            '匹配方式': '',
            '处理状态': '失败',
            '处理时间': 0.0,
            '内存使用': 0.0
        }
        
        # 检查空诊断
        if pd.isna(diagnosis) or diagnosis == "" or str(diagnosis).strip() == "":
            result['处理状态'] = '空诊断'
            result['处理时间'] = time.time() - process_start_time
            logger.info(f"[{index}] 空诊断，跳过处理")
            return result
        
        diagnosis = str(diagnosis).strip()
        logger.info(f"[{index}] 开始处理: {diagnosis[:50]}")
        
        try:
            # Step 1: LLM归一化
            step1_start = time.time()
            step1_result = self._step1_normalize(diagnosis, index)
            step1_result['步骤耗时'] = time.time() - step1_start
            result['Step1'] = step1_result
            
            if step1_result['状态'] != '成功':
                result['处理状态'] = f"Step1失败: {step1_result.get('错误信息', '未知错误')}"
                result['处理时间'] = time.time() - process_start_time
                logger.warning(f"[{index}] Step1失败: {result['处理状态']}")
                return result
            
            # 检查是否为非肿瘤诊断
            extracted_term = step1_result.get('提取的术语', '')
            extracted_code = step1_result.get('提取的编码', '')
            
            if extracted_term == "非肿瘤诊断" or (not extracted_code and not extracted_term):
                result['处理状态'] = '非肿瘤诊断或无法识别'
                result['处理时间'] = time.time() - process_start_time
                logger.info(f"[{index}] 非肿瘤诊断，跳过后续步骤")
                return result
            
            # 尝试直接编码
            if extracted_code and extracted_code in self.code_to_name:
                result['最终ICD编码'] = extracted_code
                result['最终置信度'] = 0.99
                result['匹配方式'] = '直接编码'
                result['处理状态'] = '成功'
                result['Step2'] = {'状态': '跳过（直接编码匹配）'}
                result['Step3'] = {'状态': '跳过（直接编码匹配）'}
                result['处理时间'] = time.time() - process_start_time
                logger.info(f"[{index}] ✅ 直接编码成功: {extracted_code}")
                return result
            
            # Step 2: 向量检索
            step2_start = time.time()
            search_term = extracted_term if extracted_term else diagnosis
            step2_result, candidates = self._step2_retrieve(search_term)
            step2_result['步骤耗时'] = time.time() - step2_start
            result['Step2'] = step2_result
            
            if step2_result['状态'] != '成功' or not candidates:
                result['处理状态'] = f"Step2失败: {step2_result.get('错误信息', '无候选')}"
                result['处理时间'] = time.time() - process_start_time
                logger.warning(f"[{index}] Step2失败")
                return result
            
            # Step 3: 精排
            step3_start = time.time()
            step3_result, best_match, score = self._step3_rerank(search_term, candidates)
            step3_result['步骤耗时'] = time.time() - step3_start
            result['Step3'] = step3_result
            
            if best_match and score >= self.confidence_threshold:
                result['最终ICD编码'] = best_match['ICD编码']
                result['最终置信度'] = score
                result['匹配方式'] = '检索匹配'
                result['处理状态'] = '成功'
                logger.info(f"[{index}] ✅ 检索匹配成功: {best_match['ICD编码']} (置信度: {score:.3f})")
            elif best_match:
                result['最终ICD编码'] = best_match['ICD编码']
                result['最终置信度'] = score
                result['匹配方式'] = '检索匹配(低置信度)'
                result['处理状态'] = f'低置信度({score:.3f}<{self.confidence_threshold})'
                logger.warning(f"[{index}] ⚠️ 低置信度匹配: {best_match['ICD编码']} (置信度: {score:.3f})")
            else:
                result['处理状态'] = '未找到匹配'
                logger.warning(f"[{index}] ❌ 未找到匹配")
            
            result['处理时间'] = time.time() - process_start_time
            result['内存使用'] = 0.0  # 可选的系统资源监控
            
        except Exception as e:
            result['处理状态'] = f'异常: {str(e)}'
            result['处理时间'] = time.time() - process_start_time
            logger.error(f"[{index}] 处理异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return result
    
    def _step1_normalize(self, diagnosis: str, index: int) -> Dict:
        """Step 1: LLM提取标准术语和编码"""
        step1_result = {
            '原始诊断': diagnosis,
            '原始输出': '',
            '提取的编码': '',
            '提取的术语': '',
            '是否直接编码': False,
            '使用的模型': '',
            '尝试次数': 0,
            '响应时间': 0.0,
            '状态': '失败',
            '错误信息': ''
        }
        
        # 构建提示词
        prompt = f"""你是一个医学文本处理助手。请将以下口语化诊断描述转换为ICD-10三位码（如C50）和标准疾病术语。
要求：
1. 如果诊断是肿瘤相关，请输出对应的ICD-10三位码和标准名称，格式严格为：ICD码|标准术语
   例如输入"乳房恶性肿瘤"，应输出"C50|乳房恶性肿瘤"
   例如输入"肺癌"，应输出"C34|支气管和肺恶性肿瘤"
2. 如果诊断含"术后""转移""待查""结节""占位"等，也要输出原发肿瘤的ICD码（若明确），对于无法确定性质的，可输出"无|非肿瘤诊断"
3. 如果诊断无法判断或不是肿瘤，输出"无|非肿瘤诊断"
4. 只输出一行，不要有任何解释

输入：{diagnosis}
输出："""
        
        messages = [
            {"role": "system", "content": "你是专业的医学诊断编码助手，严格遵守输出格式。"},
            {"role": "user", "content": prompt}
        ]
        
        # 调用LLM（带轮转）
        result = self.api_client.call_llm_with_rotation(
            messages, 
            self.current_model,
            PRIMARY_MODELS,
            SECONDARY_MODELS
        )
        
        if result['success']:
            content = result['result']["choices"][0]["message"]["content"].strip()
            step1_result['原始输出'] = content
            step1_result['使用的模型'] = result['model']
            step1_result['尝试次数'] = result['attempts']
            step1_result['响应时间'] = result['response_time']
            step1_result['状态'] = '成功'
            
            # 更新当前使用的模型
            self.current_model = result['model']
            
            # 解析输出
            if '|' in content:
                parts = content.split('|', 1)
                code_part = parts[0].strip()
                term_part = parts[1].strip() if len(parts) > 1 else ''
                match = re.search(r'([A-Z]\d{2})', code_part)
                if match and match.group(1) != '无':
                    step1_result['提取的编码'] = match.group(1)
                    step1_result['提取的术语'] = term_part if term_part else code_part
                    step1_result['是否直接编码'] = True
                else:
                    step1_result['提取的编码'] = ''
                    step1_result['提取的术语'] = term_part if term_part else code_part
            else:
                match = re.search(r'([A-Z]\d{2})', content)
                if match and match.group(1) != '无':
                    step1_result['提取的编码'] = match.group(1)
                    step1_result['提取的术语'] = content
                    step1_result['是否直接编码'] = True
                else:
                    step1_result['提取的编码'] = ''
                    step1_result['提取的术语'] = content
                    if content == "非肿瘤诊断":
                        step1_result['提取的术语'] = "非肿瘤诊断"
            
            logger.debug(f"[{index}] Step1输出: {content[:100]}")
        else:
            step1_result['错误信息'] = result.get('error', '未知错误')
            step1_result['尝试次数'] = result.get('attempts', 0)
            logger.error(f"[{index}] Step1失败: {step1_result['错误信息']}")
        
        return step1_result
    
    def _step2_retrieve(self, query: str) -> Tuple[Dict, List]:
        """Step 2: 向量检索候选ICD编码"""
        step2_result = {
            '查询文本': query,
            '检索结果': [],
            '候选数量': 0,
            '状态': '失败',
            '错误信息': '',
            '响应时间': 0.0
        }
        
        try:
            logger.debug(f"开始检索: '{query}'")
            
            # 获取查询向量
            start_time = time.time()
            embeddings = self.api_client.get_embeddings([query])
            step2_result['响应时间'] = time.time() - start_time
            
            if not embeddings:
                step2_result['错误信息'] = '获取查询向量失败'
                return step2_result, []
            
            query_vector = np.array(embeddings[0])
            
            # 计算余弦相似度
            similarities = np.dot(self.icd_vectors, query_vector) / (
                np.linalg.norm(self.icd_vectors, axis=1) * np.linalg.norm(query_vector) + 1e-8
            )
            
            # 获取Top-K
            top_indices = np.argsort(similarities)[-self.top_k:][::-1]
            
            candidates = []
            for idx in top_indices:
                if similarities[idx] > 0:
                    candidate_info = {
                        'ICD编码': self.icd_codes[idx],
                        '标准名称': self.icd_names[idx],
                        '检索文本': self.icd_texts[idx],
                        '相似度': float(similarities[idx])
                    }
                    candidates.append(candidate_info)
                    step2_result['检索结果'].append(candidate_info)
            
            step2_result['候选数量'] = len(candidates)
            step2_result['状态'] = '成功'
            
            if candidates:
                logger.debug(f"检索成功: {len(candidates)}个候选, 最佳: {candidates[0]['ICD编码']} (相似度: {candidates[0]['相似度']:.4f})")
            
        except Exception as e:
            step2_result['错误信息'] = str(e)
            logger.error(f"检索异常: {str(e)}")
        
        return step2_result, candidates
    
    def _step3_rerank(self, query: str, candidates: List[Dict]) -> Tuple[Dict, Optional[Dict], float]:
        """Step 3: 精排候选编码"""
        step3_result = {
            '查询文本': query,
            '精排结果': [],
            '最佳匹配': {},
            '最终分数': 0.0,
            '状态': '失败',
            '错误信息': '',
            '响应时间': 0.0
        }
        
        if not candidates:
            step3_result['错误信息'] = '无候选'
            return step3_result, None, 0.0
        
        try:
            # 准备文档列表
            documents = [c['检索文本'] for c in candidates]
            
            # 调用精排API
            start_time = time.time()
            rerank_results = self.api_client.rerank(query, documents)
            step3_result['响应时间'] = time.time() - start_time
            
            if not rerank_results:
                step3_result['错误信息'] = '精排API返回空结果'
                return step3_result, candidates[0], 0.5
            
            # 处理精排结果
            for result in rerank_results:
                idx = result['index']
                step3_result['精排结果'].append({
                    'ICD编码': candidates[idx]['ICD编码'],
                    '标准名称': candidates[idx]['标准名称'],
                    '精排分数': result['relevance_score']
                })
            
            # 找到最佳匹配
            best_result = max(rerank_results, key=lambda x: x['relevance_score'])
            best_score = best_result['relevance_score']
            best_idx = best_result['index']
            best_candidate = candidates[best_idx]
            
            step3_result['最佳匹配'] = {
                'ICD编码': best_candidate['ICD编码'],
                '标准名称': best_candidate['标准名称'],
                '分数': best_score
            }
            step3_result['最终分数'] = best_score
            step3_result['状态'] = '成功'
            
            logger.debug(f"精排成功: {best_candidate['ICD编码']} (分数: {best_score:.4f})")
            
            return step3_result, best_candidate, best_score
            
        except Exception as e:
            step3_result['错误信息'] = str(e)
            logger.error(f"精排异常: {str(e)}")
            # 失败时返回第一个候选
            return step3_result, candidates[0] if candidates else None, 0.5
    
    def get_statistics(self) -> Dict:
        """获取处理统计信息"""
        return {
            'model_stats': self.model_stats,
            'total_requests': self.request_counter,
            'current_model': self.current_model
        }

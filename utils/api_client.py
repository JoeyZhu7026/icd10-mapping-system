"""
API调用客户端 - 处理所有外部API调用
"""
import requests
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from config import API_URLS, REQUEST_TIMEOUT, ALL_MODELS
from utils.logger import setup_logger

logger = setup_logger('api')

class APIClient:
    """API调用客户端，处理所有外部API请求"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        self.request_count = 0
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = False  # 忽略SSL验证
        
    def test_connection(self) -> Tuple[bool, str]:
        """测试API连接状态"""
        try:
            test_data = {
                "model": "bge-m3",
                "input": ["测试连接"],
                "encoding_format": "float"
            }
            
            start_time = time.time()
            response = self.session.post(
                API_URLS['embed'],
                json=test_data,
                timeout=REQUEST_TIMEOUT
            )
            response_time = time.time() - start_time
            
            self.request_count += 1
            
            if response.status_code == 200:
                logger.info(f"✅ API连接正常 (响应时间: {response_time:.2f}秒)")
                return True, f"连接成功 (响应时间: {response_time:.2f}秒)"
            elif response.status_code == 401:
                logger.error("❌ API认证失败")
                return False, "API密钥认证失败"
            else:
                logger.warning(f"⚠️ API返回异常状态码: {response.status_code}")
                return False, f"API返回状态码: {response.status_code}"
                
        except requests.exceptions.Timeout:
            logger.error("❌ API连接超时")
            return False, "API连接超时"
        except Exception as e:
            logger.error(f"❌ API连接异常: {str(e)}")
            return False, f"连接异常: {str(e)}"
    
    def get_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """获取文本的向量表示"""
        data = {
            "model": "bge-m3",
            "input": texts,
            "encoding_format": "float"
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                API_URLS['embed'],
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            response_time = time.time() - start_time
            self.request_count += 1
            
            logger.debug(f"Embedding请求: {len(texts)}条文本, 响应时间: {response_time:.2f}秒")
            
            if response.status_code == 200:
                result = response.json()
                embeddings = [item['embedding'] for item in result['data']]
                return embeddings
            else:
                logger.error(f"Embedding API错误: 状态码{response.status_code}, 响应: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Embedding API超时")
            return None
        except Exception as e:
            logger.error(f"Embedding API异常: {str(e)}")
            return None
    
    def call_llm(self, messages: List[Dict], model: str) -> Dict:
        """调用LLM模型"""
        data = {
            "model": model,
            "messages": messages,
            "temperature": 0
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                API_URLS['llm'],
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            response_time = time.time() - start_time
            self.request_count += 1
            
            logger.debug(f"LLM请求: 模型={model}, 响应时间: {response_time:.2f}秒, 状态码: {response.status_code}")
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'result': response.json(),
                    'response_time': response_time,
                    'model': model
                }
            elif response.status_code == 429:
                logger.warning(f"LLM限流(429): 模型={model}")
                return {
                    'success': False,
                    'error': '限流(429)',
                    'response_time': response_time,
                    'model': model
                }
            else:
                logger.error(f"LLM错误: 模型={model}, 状态码={response.status_code}")
                return {
                    'success': False,
                    'error': f'状态码{response.status_code}',
                    'response_time': response_time,
                    'model': model
                }
                
        except requests.exceptions.Timeout:
            logger.warning(f"LLM超时: 模型={model}")
            return {
                'success': False,
                'error': '请求超时',
                'response_time': REQUEST_TIMEOUT,
                'model': model
            }
        except Exception as e:
            logger.error(f"LLM异常: 模型={model}, 错误={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'response_time': 0,
                'model': model
            }
    
    def call_llm_with_rotation(self, messages: List[Dict], current_model: str,
                              primary_models: List[str], secondary_models: List[str]) -> Dict:
        """带模型轮转的LLM调用"""
        all_models = primary_models + secondary_models
        total_models = len(all_models)
        
        # 构建尝试顺序
        try:
            start_idx = all_models.index(current_model)
        except ValueError:
            start_idx = 0
        
        attempts_order = []
        # 从当前模型开始，循环所有模型
        for i in range(total_models):
            attempts_order.append(all_models[(start_idx + i) % total_models])
        
        logger.debug(f"模型轮转顺序: {attempts_order}")
        
        # 依次尝试
        for attempt, model in enumerate(attempts_order, 1):
            logger.info(f"尝试模型 [{attempt}/{total_models}]: {model}")
            
            result = self.call_llm(messages, model)
            
            if result['success']:
                result['attempts'] = attempt
                result['model'] = model
                logger.info(f"✅ 模型调用成功: {model} (尝试{attempt}次)")
                return result
            
            logger.warning(f"❌ 模型{model}失败: {result.get('error')}, 继续下一个")
            
            # 短暂延迟避免频繁请求
            if attempt < total_models:
                time.sleep(0.5)
        
        # 所有模型都失败
        logger.error(f"所有{total_models}个模型均调用失败")
        return {
            'success': False,
            'error': '所有模型均失败',
            'attempts': total_models,
            'model': None,
            'response_time': 0
        }
    
    def rerank(self, query: str, documents: List[str]) -> Optional[List[Dict]]:
        """文档精排"""
        if not documents:
            logger.warning("精排请求: 文档列表为空")
            return None
        
        data = {
            "model": "bge-reranker-v2-m3",
            "query": query,
            "documents": documents
        }
        
        try:
            start_time = time.time()
            response = self.session.post(
                API_URLS['rerank'],
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            response_time = time.time() - start_time
            self.request_count += 1
            
            logger.debug(f"精排请求: {len(documents)}个文档, 响应时间: {response_time:.2f}秒")
            
            if response.status_code == 200:
                results = response.json()['results']
                # 按相关性分数排序
                results.sort(key=lambda x: x['relevance_score'], reverse=True)
                return results
            else:
                logger.error(f"精排API错误: 状态码{response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("精排API超时")
            return None
        except Exception as e:
            logger.error(f"精排API异常: {str(e)}")
            return None
    
    def close(self):
        """关闭会话"""
        self.session.close()

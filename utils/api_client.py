"""
API调用客户端
"""
import requests
import time
import json
from typing import List, Dict, Any
from config import API_URLS, REQUEST_TIMEOUT
from utils.logger import setup_logger

logger = setup_logger('api')

class APIClient:
    """API调用客户端"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        self.request_count = 0
        
    def test_connection(self) -> bool:
        """测试API连接"""
        try:
            test_data = {
                "model": "bge-m3",
                "input": ["测试"],
                "encoding_format": "float"
            }
            response = requests.post(
                API_URLS['embed'],
                headers=self.headers,
                json=test_data,
                verify=False,
                timeout=REQUEST_TIMEOUT
            )
            return response.status_code == 200
        except:
            return False
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """获取文本向量"""
        data = {
            "model": "bge-m3",
            "input": texts,
            "encoding_format": "float"
        }
        
        response = requests.post(
            API_URLS['embed'],
            headers=self.headers,
            json=data,
            verify=False,
            timeout=REQUEST_TIMEOUT
        )
        
        self.request_count += 1
        
        if response.status_code == 200:
            result = response.json()
            return [item['embedding'] for item in result['data']]
        else:
            raise Exception(f"Embedding API错误: {response.status_code}")
    
    def call_llm(self, messages: List[Dict], model: str) -> Dict:
        """调用LLM"""
        data = {
            "model": model,
            "messages": messages,
            "temperature": 0
        }
        
        start_time = time.time()
        response = requests.post(
            API_URLS['llm'],
            headers=self.headers,
            json=data,
            verify=False,
            timeout=REQUEST_TIMEOUT
        )
        response_time = time.time() - start_time
        
        self.request_count += 1
        
        if response.status_code == 200:
            return {
                'success': True,
                'result': response.json(),
                'response_time': response_time
            }
        else:
            return {
                'success': False,
                'error': f"状态码: {response.status_code}",
                'response_time': response_time
            }
    
    def rerank(self, query: str, documents: List[str]) -> List[Dict]:
        """精排"""
        data = {
            "model": "bge-reranker-v2-m3",
            "query": query,
            "documents": documents
        }
        
        response = requests.post(
            API_URLS['rerank'],
            headers=self.headers,
            json=data,
            verify=False,
            timeout=REQUEST_TIMEOUT
        )
        
        self.request_count += 1
        
        if response.status_code == 200:
            return response.json()['results']
        else:
            raise Exception(f"Rerank API错误: {response.status_code}")
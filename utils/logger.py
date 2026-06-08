"""
日志系统配置
"""
import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logger(name: str = 'main', log_dir: str = 'logs') -> logging.Logger:
    """设置日志记录器"""
    
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 创建logger
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # 文件处理器 - 详细日志
    log_file = log_path / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 错误日志单独文件
    error_file = log_path / f"{name}_error_{datetime.now().strftime('%Y%m%d')}.log"
    error_handler = logging.FileHandler(error_file, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)
    
    # 控制台处理器 - 只显示警告及以上
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger

class APILogger:
    """API请求专用日志"""
    
    def __init__(self, log_dir: str = 'logs'):
        self.log_path = Path(log_dir)
        self.log_path.mkdir(parents=True, exist_ok=True)
        
        # 创建API日志文件
        self.log_file = self.log_path / f"api_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        self.logger = logging.getLogger('api_requests')
        self.logger.setLevel(logging.DEBUG)
        
        # 文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
    def log_request(self, method: str, url: str, data: dict = None, 
                   response_status: int = None, response_time: float = None):
        """记录API请求"""
        message = f"API请求 - {method} {url}"
        if data:
            # 不记录完整的API密钥
            safe_data = {k: v for k, v in data.items() if k not in ['Authorization']}
            message += f"\n  请求数据: {str(safe_data)[:500]}"
        if response_status:
            message += f"\n  响应状态: {response_status}"
        if response_time:
            message += f"\n  响应时间: {response_time:.3f}秒"
        
        self.logger.info(message)
    
    def log_error(self, error_msg: str, exception: Exception = None):
        """记录错误"""
        message = f"API错误: {error_msg}"
        if exception:
            message += f"\n  异常详情: {str(exception)}"
        self.logger.error(message)

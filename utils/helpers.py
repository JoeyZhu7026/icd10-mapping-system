"""
辅助工具函数
"""
import os
import re
import zipfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

def get_smart_column_names(diag_col: str, existing_columns: List[str]) -> List[str]:
    """智能生成不冲突的列名"""
    base_suffixes = ['.icd10', '.score', '.status', '.method']
    proposed_cols = [f"{diag_col}{suffix}" for suffix in base_suffixes]
    
    # 检查是否有冲突
    if any(col in existing_columns for col in proposed_cols):
        # 找到最大的编号
        max_num = 0
        for col in existing_columns:
            for suffix in base_suffixes:
                pattern = re.escape(f"{diag_col}{suffix}")
                match = re.match(rf'{pattern}\((\d+)\)$', col)
                if match:
                    num = int(match.group(1))
                    max_num = max(max_num, num)
        
        next_num = max_num + 1
        return [f"{diag_col}{suffix}({next_num})" for suffix in base_suffixes]
    
    return proposed_cols

def create_zip_archive(source_dir: str, output_path: str = None) -> str:
    """创建ZIP压缩包"""
    source_path = Path(source_dir)
    
    if output_path is None:
        output_path = f"{source_dir}.zip"
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(source_path))
                zipf.write(file_path, arcname)
    
    return output_path

def clean_old_results(results_dir: str = 'results', max_age_days: int = 7):
    """清理旧的结果文件"""
    results_path = Path(results_dir)
    if not results_path.exists():
        return
    
    import time
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 3600
    
    for item in results_path.iterdir():
        if item.is_dir():
            # 检查目录的修改时间
            if current_time - item.stat().st_mtime > max_age_seconds:
                shutil.rmtree(item)
                print(f"清理旧结果: {item}")
        elif item.suffix == '.zip':
            if current_time - item.stat().st_mtime > max_age_seconds:
                item.unlink()
                print(f"清理旧压缩包: {item}")

def validate_csv_format(file_path: str) -> Dict[str, Any]:
    """验证CSV文件格式"""
    try:
        df = pd.read_csv(file_path, nrows=5)
        
        result = {
            'valid': True,
            'rows_preview': len(df),
            'columns': df.columns.tolist(),
            'column_count': len(df.columns),
            'sample_data': df.head(3).to_dict('records'),
            'error': None
        }
        
        return result
        
    except Exception as e:
        return {
            'valid': False,
            'rows_preview': 0,
            'columns': [],
            'column_count': 0,
            'sample_data': [],
            'error': str(e)
        }

def extract_icd_code(text: str) -> str:
    """从文本中提取ICD-10编码"""
    # 匹配ICD-10编码模式: 字母+2-3位数字
    pattern = r'([A-Z]\d{2,3})'
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return ''

def format_diagnosis_term(term: str) -> str:
    """格式化诊断术语"""
    # 去除多余空格
    term = re.sub(r'\s+', ' ', term).strip()
    # 统一标点符号
    term = term.replace('，', ',').replace('。', '.')
    return term

def get_file_info(file_path: str) -> Dict[str, Any]:
    """获取文件信息"""
    path = Path(file_path)
    if not path.exists():
        return {'exists': False}
    
    return {
        'exists': True,
        'name': path.name,
        'stem': path.stem,
        'suffix': path.suffix,
        'size': path.stat().st_size,
        'size_mb': round(path.stat().st_size / (1024 * 1024), 2),
        'modified': path.stat().st_mtime,
        'is_file': path.is_file(),
        'is_dir': path.is_dir()
    }

def ensure_directory(path: str) -> str:
    """确保目录存在"""
    dir_path = Path(path)
    dir_path.mk

import streamlit as st
import pandas as pd
import os
import zipfile
import shutil
from datetime import datetime
from pathlib import Path

# 页面配置必须是第一个 Streamlit 命令
st.set_page_config(
    page_title="ICD-10编码映射系统",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 导入自定义模块
from icd_processor import ICDProcessor
from utils.logger import setup_logger

# 初始化日志
logger = setup_logger()

def main():
    st.title("🏥 ICD-10 诊断编码映射系统")
    st.markdown("---")
    
    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 系统配置")
        
        # API密钥输入
        api_key = st.text_input(
            "🔑 API密钥", 
            type="password", 
            placeholder="请输入API密钥",
            help="用于调用大语言模型API"
        )
        
        # 文件上传
        uploaded_file = st.file_uploader(
            "📁 上传CSV文件", 
            type=['csv'],
            help="包含诊断描述的CSV文件"
        )
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.success(f"✅ 成功加载 {len(df)} 条记录")
                
                # 选择诊断列
                diag_col = st.selectbox(
                    "🎯 选择诊断描述列",
                    options=df.columns.tolist(),
                    index=0,
                    help="选择包含口语化诊断描述的列"
                )
                
                # 高级设置
                with st.expander("🔧 高级设置"):
                    confidence_threshold = st.slider(
                        "置信度阈值", 
                        min_value=0.0, max_value=1.0, 
                        value=0.5, step=0.05
                    )
                    
                    top_k = st.number_input(
                        "检索候选数", 
                        min_value=5, max_value=50, 
                        value=10
                    )
                
                # 开始处理按钮
                if st.button("🚀 开始处理", type="primary", use_container_width=True):
                    if not api_key:
                        st.error("❌ 请先输入API密钥")
                    else:
                        process_data(uploaded_file, df, diag_col, api_key, 
                                   confidence_threshold, top_k)
                        
            except Exception as e:
                st.error(f"❌ 文件加载失败: {str(e)}")
        
        # 加载示例数据
        if st.button("📋 加载示例数据", use_container_width=True):
            sample_path = Path("data/sample/示例诊断数据.csv")
            if sample_path.exists():
                # 这里可以加载示例数据展示
                st.info("示例数据加载功能开发中...")

def process_data(uploaded_file, df, diag_col, api_key, confidence_threshold, top_k):
    """处理数据的主函数"""
    
    # 创建进度显示
    progress_bar = st.progress(0)
    status_text = st.empty()
    step_text = st.empty()
    stats_container = st.empty()
    
    try:
        # 1. 保存上传文件
        file_name = Path(uploaded_file.name).stem
        output_dir = Path(f"results/{file_name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir = output_dir / "log"
        log_dir.mkdir(exist_ok=True)
        
        # 2. 初始化处理器
        status_text.text("📚 正在初始化系统...")
        processor = ICDProcessor(
            api_key=api_key,
            confidence_threshold=confidence_threshold,
            top_k=top_k
        )
        
        # 3. 加载知识库
        status_text.text("📚 加载ICD知识库并构建向量索引...")
        progress_bar.progress(10)
        
        icd_lib_path = "data/icd10_data/ICD-10医保1.0版.总表.三位码.别名.csv"
        if not processor.load_knowledge_base(icd_lib_path):
            st.error("❌ ICD知识库加载失败")
            return
        
        progress_bar.progress(30)
        
        # 4. 处理数据
        status_text.text("🔄 正在处理诊断描述...")
        
        results = []
        total = len(df)
        
        for idx, row in df.iterrows():
            diagnosis = row[diag_col]
            
            # 处理单条记录
            result = processor.process_single(diagnosis, idx)
            results.append(result)
            
            # 更新进度
            progress = 30 + int((idx + 1) / total * 60)
            progress_bar.progress(progress)
            
            # 更新状态显示
            step_text.markdown(f"""
            **处理进度**: {idx+1}/{total}  
            **当前模型**: {result.get('Step1', {}).get('使用的模型', 'N/A')}  
            **当前诊断**: {diagnosis[:50]}...
            """)
            
            # 每10条更新统计
            if (idx + 1) % 10 == 0:
                success_count = sum(1 for r in results if r['处理状态'] == '成功')
                stats_container.info(f"""
                📊 实时统计:  
                已处理: {idx+1} | 成功: {success_count} | 成功率: {success_count/(idx+1)*100:.1f}%
                """)
        
        progress_bar.progress(100)
        status_text.text("✅ 处理完成！正在生成结果文件...")
        
        # 5. 保存结果
        save_results(df, results, diag_col, output_dir, file_name)
        
        # 6. 提供下载
        st.success(f"✅ 处理完成！成功编码 {success_count}/{total} 条记录")
        provide_download_section(output_dir, df, results)
        
        # 7. 清理临时文件
        logger.info(f"处理完成，结果保存在: {output_dir}")
        
    except Exception as e:
        st.error(f"❌ 处理过程出错: {str(e)}")
        logger.error(f"处理失败: {str(e)}", exc_info=True)

def save_results(df, results, diag_col, output_dir, file_name):
    """保存处理结果"""
    
    # 提取结果列
    icd_codes = [r['最终ICD编码'] for r in results]
    scores = [r['最终置信度'] for r in results]
    statuses = [r['处理状态'] for r in results]
    methods = [r['匹配方式'] for r in results]
    
    # 智能列名
    new_cols = [f"{diag_col}.icd10", f"{diag_col}.score", 
                f"{diag_col}.status", f"{diag_col}.method"]
    
    # 插入新列
    diag_idx = df.columns.get_loc(diag_col)
    df.insert(diag_idx + 1, new_cols[0], icd_codes)
    df.insert(diag_idx + 2, new_cols[1], scores)
    df.insert(diag_idx + 3, new_cols[2], statuses)
    df.insert(diag_idx + 4, new_cols[3], methods)
    
    # 保存
    output_file = output_dir / f"{file_name}_icd10结果.csv"
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    # 保存详细日志
    import json
    log_file = output_dir / "log" / "处理详情.json"
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def provide_download_section(output_dir, df, results):
    """提供下载和预览"""
    
    st.divider()
    st.subheader("📥 下载结果")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 创建ZIP压缩包
        zip_path = f"{output_dir}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                    zipf.write(file_path, arcname)
        
        # 下载按钮
        with open(zip_path, 'rb') as f:
            st.download_button(
                label=f"📦 下载完整结果包 ({output_dir.name}.zip)",
                data=f,
                file_name=f"{output_dir.name}.zip",
                mime="application/zip",
                use_container_width=True
            )
    
    with col2:
        # 统计信息
        success_count = sum(1 for r in results if r['处理状态'] == '成功')
        st.metric("总记录数", len(results))
        st.metric("成功编码", success_count)
        st.metric("编码成功率", f"{success_count/len(results)*100:.1f}%")
    
    # 结果预览
    with st.expander("📊 结果预览"):
        preview_df = df[[col for col in df.columns if col.endswith(('.icd10', '.score', '.status', '.method'))]]
        st.dataframe(preview_df.head(20), use_container_width=True)

if __name__ == "__main__":
    main()
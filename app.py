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
        
        # 初始化session state用于存储上传的文件
        if 'uploaded_file' not in st.session_state:
            st.session_state.uploaded_file = None
        if 'df' not in st.session_state:
            st.session_state.df = None
        if 'file_name' not in st.session_state:
            st.session_state.file_name = None
        
        # 文件上传区域
        uploaded_file = st.file_uploader(
            "📁 上传CSV文件", 
            type=['csv'],
            help="包含诊断描述的CSV文件"
        )
        
        # 加载示例数据按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📋 加载示例数据", use_container_width=True):
                sample_path = Path("data/sample/示例诊断数据.csv")
                if sample_path.exists():
                    try:
                        # 读取示例文件
                        with open(sample_path, 'rb') as f:
                            sample_bytes = f.read()
                        
                        # 创建一个类似上传文件的对象
                        from io import BytesIO
                        st.session_state.uploaded_file = BytesIO(sample_bytes)
                        st.session_state.uploaded_file.name = "示例诊断数据.csv"
                        st.session_state.df = pd.read_csv(sample_path)
                        st.session_state.file_name = "示例诊断数据"
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 示例数据加载失败: {str(e)}")
                else:
                    st.warning("⚠️ 示例数据文件不存在，请检查 data/sample/示例诊断数据.csv 路径")
        
        # 清除数据按钮
        with col2:
            if st.button("🗑️ 清除数据", use_container_width=True):
                st.session_state.uploaded_file = None
                st.session_state.df = None
                st.session_state.file_name = None
                st.rerun()
        
        # 处理上传的文件或示例数据
        current_df = None
        current_file_name = None
        
        if uploaded_file is not None:
            # 用户上传了文件
            try:
                current_df = pd.read_csv(uploaded_file)
                current_file_name = Path(uploaded_file.name).stem
                st.success(f"✅ 成功加载 {len(current_df)} 条记录")
            except Exception as e:
                st.error(f"❌ 文件加载失败: {str(e)}")
        elif st.session_state.uploaded_file is not None:
            # 使用示例数据
            try:
                current_df = st.session_state.df
                current_file_name = st.session_state.file_name
                st.success(f"✅ 成功加载示例数据 ({len(current_df)} 条记录)")
            except Exception as e:
                st.error(f"❌ 示例数据读取失败: {str(e)}")
        
        if current_df is not None:
            # 选择诊断列
            diag_col = st.selectbox(
                "🎯 选择诊断描述列",
                options=current_df.columns.tolist(),
                index=0,
                help="选择包含口语化诊断描述的列"
            )
            
            # 高级设置
            with st.expander("🔧 高级设置"):
                confidence_threshold = st.slider(
                    "置信度阈值", 
                    min_value=0.0, max_value=1.0, 
                    value=0.5, step=0.05,
                    help="低于此阈值的匹配结果将被标记为低置信度"
                )
                
                top_k = st.number_input(
                    "检索候选数", 
                    min_value=5, max_value=50, 
                    value=10,
                    help="向量检索时返回的候选数量"
                )
            
            # 开始处理按钮
            if st.button("🚀 开始处理", type="primary", use_container_width=True):
                if not api_key:
                    st.error("❌ 请先输入API密钥")
                else:
                    process_data(current_df, current_file_name, diag_col, api_key, 
                               confidence_threshold, top_k)
        
        # 数据预览
        if current_df is not None:
            with st.expander("📊 数据预览"):
                st.dataframe(current_df.head(10), use_container_width=True)

def process_data(df, file_name, diag_col, api_key, confidence_threshold, top_k):
    """处理数据的主函数"""
    
    # 创建进度显示
    progress_bar = st.progress(0)
    status_text = st.empty()
    step_text = st.empty()
    stats_container = st.empty()
    main_container = st.container()
    
    try:
        with main_container:
            st.subheader("🔄 处理进度")
        
        # 1. 创建输出目录
        output_dir = Path(f"results/{file_name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir = output_dir / "log"
        log_dir.mkdir(exist_ok=True)
        
        # 2. 初始化处理器
        status_text.text("📚 正在初始化系统...")
        progress_bar.progress(5)
        
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
            with main_container:
                st.error("❌ ICD知识库加载失败，请检查文件路径")
            return
        
        progress_bar.progress(30)
        
        # 4. 处理数据
        status_text.text("🔄 正在处理诊断描述...")
        
        results = []
        total = len(df)
        success_count = 0
        
        for idx, row in df.iterrows():
            diagnosis = row[diag_col]
            
            # 处理单条记录
            result = processor.process_single(diagnosis, idx)
            results.append(result)
            
            if result['处理状态'] == '成功':
                success_count += 1
            
            # 更新进度
            progress = 30 + int((idx + 1) / total * 60)
            progress_bar.progress(progress)
            
            # 更新状态显示
            step_text.markdown(f"""
            **处理进度**: {idx+1}/{total}  
            **当前模型**: {result.get('Step1', {}).get('使用的模型', 'N/A')}  
            **成功率**: {success_count/(idx+1)*100:.1f}%
            """)
            
            # 每10条更新统计
            if (idx + 1) % 10 == 0 or (idx + 1) == total:
                stats_container.info(f"""
                📊 实时统计:  
                已处理: {idx+1}/{total} | 成功: {success_count} | 成功率: {success_count/(idx+1)*100:.1f}%
                """)
        
        progress_bar.progress(95)
        status_text.text("✅ 处理完成！正在生成结果文件...")
        
        # 5. 保存结果
        save_results(df, results, diag_col, output_dir, file_name)
        
        progress_bar.progress(100)
        
        # 6. 显示结果
        with main_container:
            st.success(f"✅ 处理完成！成功编码 {success_count}/{total} 条记录")
            provide_download_section(output_dir, df, results)
        
        logger.info(f"处理完成: {file_name}, 成功率: {success_count}/{total}")
        
    except Exception as e:
        with main_container:
            st.error(f"❌ 处理过程出错: {str(e)}")
        logger.error(f"处理失败: {str(e)}", exc_info=True)

def save_results(df, results, diag_col, output_dir, file_name):
    """保存处理结果"""
    
    # 提取结果列
    icd_codes = [r['最终ICD编码'] for r in results]
    scores = [r['最终置信度'] for r in results]
    statuses = [r['处理状态'] for r in results]
    methods = [r['匹配方式'] for r in results]
    
    # 生成列名
    new_cols = [
        f"{diag_col}.icd10", 
        f"{diag_col}.score", 
        f"{diag_col}.status", 
        f"{diag_col}.method"
    ]
    
    # 在诊断列右边插入新列
    diag_idx = df.columns.get_loc(diag_col)
    df.insert(diag_idx + 1, new_cols[0], icd_codes)
    df.insert(diag_idx + 2, new_cols[1], scores)
    df.insert(diag_idx + 3, new_cols[2], statuses)
    df.insert(diag_idx + 4, new_cols[3], methods)
    
    # 保存主结果文件
    output_file = output_dir / f"{file_name}_icd10结果.csv"
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    # 保存详细日志
    import json
    log_file = output_dir / "log" / "处理详情.json"
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 保存统计摘要
    summary_data = []
    for r in results:
        summary_data.append({
            '序号': r['序号'],
            '原始诊断': r['原始诊断'],
            '最终ICD编码': r['最终ICD编码'],
            '置信度': r['最终置信度'],
            '匹配方式': r['匹配方式'],
            '处理状态': r['处理状态'],
            '处理时间': r.get('处理时间', 0)
        })
    
    summary_file = output_dir / "log" / "处理摘要.csv"
    pd.DataFrame(summary_data).to_csv(summary_file, index=False, encoding='utf-8-sig')
    
    logger.info(f"结果已保存到: {output_dir}")

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
        total = len(results)
        success_count = sum(1 for r in results if r['处理状态'] == '成功')
        direct_count = sum(1 for r in results if r['匹配方式'] == '直接编码')
        retrieval_count = sum(1 for r in results if r['匹配方式'] == '检索匹配')
        
        st.metric("总记录数", total)
        st.metric("成功编码", success_count)
        st.metric("编码成功率", f"{success_count/total*100:.1f}%")
        st.metric("直接编码", direct_count)
        st.metric("检索匹配", retrieval_count)
    
    # 结果预览
    with st.expander("📊 结果预览"):
        # 只显示新增的列
        result_cols = [col for col in df.columns if col.endswith(('.icd10', '.score', '.status', '.method'))]
        preview_cols = [df.columns[0]] + result_cols  # 第一列+结果列
        st.dataframe(df[preview_cols].head(20), use_container_width=True)

if __name__ == "__main__":
    main()

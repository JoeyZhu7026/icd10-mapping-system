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
    initial_sidebar_state="collapsed"
)

# 导入自定义模块
from icd_processor import ICDProcessor
from utils.logger import setup_logger
from utils.api_client import APIClient

# 初始化日志
logger = setup_logger()

# 自定义CSS样式
st.markdown("""
<style>
    /* 让按钮和输入框高度一致 */
    .stButton > button {
        height: 42px !important;
        margin-top: 0px !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
    
    /* 验证状态框样式 */
    .status-box {
        padding: 8px 16px;
        border-radius: 4px;
        text-align: center;
        font-size: 14px;
        height: 42px;
        line-height: 26px;
        margin-top: 0px;
    }
    .status-verified {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .status-unverified {
        background-color: #e2e3e5;
        color: #383d41;
        border: 1px solid #d6d8db;
    }
</style>
""", unsafe_allow_html=True)

def verify_api_key(api_key):
    """验证API密钥是否有效"""
    if not api_key or api_key.strip() == "":
        return False, "请输入API密钥"
    
    try:
        client = APIClient(api_key)
        success, message = client.test_connection()
        return success, message
    except Exception as e:
        return False, f"验证失败: {str(e)}"

def clear_data():
    """清除所有数据"""
    st.session_state.uploaded_file = None
    st.session_state.df = None
    st.session_state.file_name = None
    st.session_state.processing_done = False
    st.session_state.data_source = None
    if 'uploader_key' in st.session_state:
        st.session_state.uploader_key += 1
    else:
        st.session_state.uploader_key = 1

def get_icd_knowledge_base_download_button():
    """生成下载ICD知识库文件的按钮和逻辑"""
    icd_lib_path = Path("data/icd10_data/ICD-10医保1.0版.总表.三位码.别名.csv")
    
    if not icd_lib_path.exists():
        st.warning("⚠️ 知识库文件不存在")
        return
    
    # 读取文件内容
    with open(icd_lib_path, 'rb') as f:
        file_data = f.read()
    
    # 获取文件信息
    file_size_mb = len(file_data) / (1024 * 1024)
    file_name = icd_lib_path.name
    
    # 创建下载按钮
    st.download_button(
        label=f"📥 下载知识库 ({file_size_mb:.1f}MB)",
        data=file_data,
        file_name=file_name,
        mime="text/csv",
        use_container_width=True,
        help="下载ICD-10全疾病编码知识库文件（CSV格式）",
        key="download_icd_kb"
    )

def main():
    st.title("🏥 ICD-10 诊断编码映射系统")
    st.markdown("---")
    
    # 初始化session state
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'file_name' not in st.session_state:
        st.session_state.file_name = None
    if 'api_verified' not in st.session_state:
        st.session_state.api_verified = False
    if 'processing_done' not in st.session_state:
        st.session_state.processing_done = False
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0
    if 'data_source' not in st.session_state:
        st.session_state.data_source = None
    if 'verify_message' not in st.session_state:
        st.session_state.verify_message = None
    if 'verify_success' not in st.session_state:
        st.session_state.verify_success = None
    
    # ========== 第一部分：API密钥配置 ==========
    st.subheader("🔑 API密钥配置")
    
    col_key1, col_key2, col_key3 = st.columns([3, 1, 1])
    
    with col_key1:
        api_key = st.text_input(
            "API密钥", 
            type="password", 
            placeholder="请输入您的API密钥",
            help="用于调用大语言模型API",
            label_visibility="collapsed"
        )
    
    with col_key2:
        if st.button("🔍 验证密钥", use_container_width=True):
            if not api_key:
                st.session_state.verify_message = "⚠️ 请先输入API密钥"
                st.session_state.verify_success = False
            else:
                with st.spinner("正在验证API密钥..."):
                    success, message = verify_api_key(api_key)
                    st.session_state.verify_message = f"{'✅' if success else '❌'} {message}"
                    st.session_state.verify_success = success
                    st.session_state.api_verified = success
            st.rerun()
    
    with col_key3:
        if st.session_state.api_verified:
            st.markdown('<div class="status-box status-verified">✅ 已验证</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-box status-unverified">⭕ 未验证</div>', unsafe_allow_html=True)
    
    # 验证结果消息显示在下方（全宽度）
    if st.session_state.verify_message is not None:
        if st.session_state.verify_success:
            st.success(st.session_state.verify_message)
        else:
            st.error(st.session_state.verify_message)
    
    st.markdown("---")
    
    # ========== 第二部分：数据上传 ==========
    st.subheader("📁 数据上传")
    
    # 横向排列：上传框占0.5，加载示例占0.25，清除数据占0.25
    col_upload, col_sample, col_clear = st.columns([0.5, 0.25, 0.25])
    
    with col_upload:
        uploaded_file = st.file_uploader(
            "上传CSV文件", 
            type=['csv'],
            help="包含诊断描述的CSV文件",
            label_visibility="collapsed",
            key=f"file_uploader_{st.session_state.uploader_key}"
        )
    
    with col_sample:
        if st.button("📋 加载示例数据", use_container_width=True):
            sample_path = Path("data/sample/示例诊断数据.csv")
            if sample_path.exists():
                try:
                    clear_data()
                    
                    with open(sample_path, 'rb') as f:
                        sample_bytes = f.read()
                    
                    from io import BytesIO
                    st.session_state.uploaded_file = BytesIO(sample_bytes)
                    st.session_state.uploaded_file.name = "示例诊断数据.csv"
                    st.session_state.df = pd.read_csv(sample_path)
                    st.session_state.file_name = "示例诊断数据"
                    st.session_state.data_source = 'sample'
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 示例数据加载失败: {str(e)}")
            else:
                st.warning("⚠️ 示例数据文件不存在")
    
    with col_clear:
        if st.button("🗑️ 清除数据", use_container_width=True):
            clear_data()
            st.rerun()
    
    # 处理上传的文件或示例数据
    current_df = None
    current_file_name = None
    
    if uploaded_file is not None:
        try:
            current_df = pd.read_csv(uploaded_file)
            current_file_name = Path(uploaded_file.name).stem
            st.session_state.df = current_df
            st.session_state.file_name = current_file_name
            st.session_state.data_source = 'upload'
            st.success(f"✅ 成功加载 {len(current_df)} 条记录")
        except Exception as e:
            st.error(f"❌ 文件加载失败: {str(e)}")
            current_df = None
    elif st.session_state.data_source == 'sample' and st.session_state.df is not None:
        current_df = st.session_state.df
        current_file_name = st.session_state.file_name
        st.success(f"✅ 成功加载示例数据 ({len(current_df)} 条记录)")
    
    # ========== 第三部分：列选择和参数配置 ==========
    if current_df is not None:
        st.markdown("---")
        st.subheader("⚙️ 处理配置")

        col_config1, col_config2, col_config3, col_config4 = st.columns([1, 1, 1, 0.6])
        
        with col_config1:
            diag_col = st.selectbox(
                "🎯 诊断描述列",
                options=current_df.columns.tolist(),
                index=0,
                help="选择包含口语化诊断描述的列"
            )
        
        with col_config2:
            confidence_threshold = st.slider(
                "📊 置信度阈值", 
                min_value=0.0, max_value=1.0, 
                value=0.5, step=0.05,
                help="低于此阈值的匹配结果将被标记为低置信度"
            )
        
        with col_config3:
            top_k = st.number_input(
                "🔍 检索候选数", 
                min_value=5, max_value=50, 
                value=10,
                help="向量检索时返回的候选数量"
            )
        
        with col_config4:
            # 添加一些上边距使按钮与上方对齐
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            get_icd_knowledge_base_download_button()
        
        with st.expander("📊 数据预览（点击展开）"):
            st.dataframe(current_df.head(10), use_container_width=True)
        
        st.markdown("---")
        
        # ========== 第四部分：开始处理 ==========
        if st.button("🚀 开始处理", type="primary", use_container_width=True):
            if not api_key:
                st.error("❌ 请先输入API密钥")
            elif not st.session_state.api_verified:
                with st.spinner("正在验证API密钥..."):
                    success, message = verify_api_key(api_key)
                    st.session_state.verify_message = f"{'✅' if success else '❌'} {message}"
                    st.session_state.verify_success = success
                    st.session_state.api_verified = success
                    if not success:
                        st.rerun()
            
            if st.session_state.api_verified:
                process_data(current_df, current_file_name, diag_col, api_key, 
                           confidence_threshold, top_k)
    
    # ========== 第五部分：结果展示和下载 ==========
    if st.session_state.processing_done and st.session_state.file_name:
        st.markdown("---")
        st.subheader("📊 处理结果")
        
        output_dir = Path(f"results/{st.session_state.file_name}")
        if output_dir.exists():
            zip_path = f"{output_dir}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                        zipf.write(file_path, arcname)
            
            with open(zip_path, 'rb') as f:
                st.download_button(
                    label=f"📦 下载完整结果包 ({output_dir.name}.zip)",
                    data=f,
                    file_name=f"{output_dir.name}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

def process_data(df, file_name, diag_col, api_key, confidence_threshold, top_k):
    """处理数据的主函数"""
    
    st.markdown("---")
    st.subheader("🔄 处理进度")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    step_text = st.empty()
    stats_container = st.empty()
    
    try:
        output_dir = Path(f"results/{file_name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir = output_dir / "log"
        log_dir.mkdir(exist_ok=True)
        
        status_text.text("📚 正在初始化系统...")
        progress_bar.progress(5)
        
        processor = ICDProcessor(
            api_key=api_key,
            confidence_threshold=confidence_threshold,
            top_k=top_k
        )
        
        status_text.text("📚 加载ICD知识库并构建向量索引...")
        progress_bar.progress(10)
        
        icd_lib_path = "data/icd10_data/ICD-10医保1.0版.总表.三位码.别名.csv"
        if not processor.load_knowledge_base(icd_lib_path):
            st.error("❌ ICD知识库加载失败，请检查文件路径")
            return
        
        progress_bar.progress(30)
        
        status_text.text("🔄 正在处理诊断描述...")
        
        results = []
        total = len(df)
        success_count = 0
        
        for idx, row in df.iterrows():
            diagnosis = row[diag_col]
            
            result = processor.process_single(diagnosis, idx)
            results.append(result)
            
            if result['处理状态'] == '成功':
                success_count += 1
            
            progress = 30 + int((idx + 1) / total * 60)
            progress_bar.progress(progress)
            
            step_text.markdown(f"""
            **处理进度**: {idx+1}/{total}  
            **当前模型**: {result.get('Step1', {}).get('使用的模型', 'N/A')}  
            **当前诊断**: {str(diagnosis)[:50]}...
            """)
            
            if (idx + 1) % 5 == 0 or (idx + 1) == total:
                stats_container.info(f"""
                📊 实时统计:  
                已处理: {idx+1}/{total} | 成功: {success_count} | 成功率: {success_count/(idx+1)*100:.1f}%
                """)
        
        progress_bar.progress(95)
        status_text.text("✅ 处理完成！正在生成结果文件...")
        
        save_results(df, results, diag_col, output_dir, file_name)
        
        progress_bar.progress(100)
        status_text.text("✅ 处理完成！")
        
        st.success(f"✅ 处理完成！成功编码 {success_count}/{total} 条记录")
        
        col_stat1, col_stat2, col_stat3, col_stat4, col_stat5 = st.columns(5)
        
        with col_stat1:
            st.metric("总记录数", total)
        with col_stat2:
            st.metric("成功编码", success_count)
        with col_stat3:
            st.metric("编码成功率", f"{success_count/total*100:.1f}%")
        with col_stat4:
            direct_count = sum(1 for r in results if r['匹配方式'] == '直接编码')
            st.metric("直接编码", direct_count)
        with col_stat5:
            retrieval_count = sum(1 for r in results if r['匹配方式'] == '检索匹配')
            st.metric("检索匹配", retrieval_count)
        
        with st.expander("📊 结果预览（点击展开）"):
            result_cols = [col for col in df.columns if col.endswith(('.icd10', '.score', '.status', '.method'))]
            preview_cols = [df.columns[0]] + result_cols
            st.dataframe(df[preview_cols].head(20), use_container_width=True)
        
        st.session_state.processing_done = True
        st.session_state.file_name = file_name
        
        logger.info(f"处理完成: {file_name}, 成功率: {success_count}/{total}")
        
    except Exception as e:
        st.error(f"❌ 处理过程出错: {str(e)}")
        logger.error(f"处理失败: {str(e)}", exc_info=True)

def save_results(df, results, diag_col, output_dir, file_name):
    """保存处理结果"""
    
    icd_codes = [r['最终ICD编码'] for r in results]
    scores = [r['最终置信度'] for r in results]
    statuses = [r['处理状态'] for r in results]
    methods = [r['匹配方式'] for r in results]
    
    new_cols = [
        f"{diag_col}.icd10", 
        f"{diag_col}.score", 
        f"{diag_col}.status", 
        f"{diag_col}.method"
    ]
    
    diag_idx = df.columns.get_loc(diag_col)
    df.insert(diag_idx + 1, new_cols[0], icd_codes)
    df.insert(diag_idx + 2, new_cols[1], scores)
    df.insert(diag_idx + 3, new_cols[2], statuses)
    df.insert(diag_idx + 4, new_cols[3], methods)
    
    output_file = output_dir / f"{file_name}_icd10结果.csv"
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    import json
    log_file = output_dir / "log" / "处理详情.json"
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
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

if __name__ == "__main__":
    main()

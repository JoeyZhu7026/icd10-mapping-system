# 🏥 ICD-10 智能编码映射系统

> **复旦大学"未来智造（AI Agent）工程师"训练营参赛项目**  
> AI 智能体赋能医疗诊断标准化，让口语化诊断秒变标准 ICD-10 编码

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://icd10-mapping-system-pe8ksc4dp9rvb72zu3rzwf.streamlit.app/)

---

## 📖 项目简介

在医疗领域，医生记录的诊断描述往往是口语化的（如"乳房恶性肿瘤""肺癌术后"），而医保报销、病历统计等场景需要标准的 ICD-10 编码（如 C50、C34）。

本项目基于 **多模型 LLM 轮转策略 + 向量检索 + 精排** 技术路线，构建了一个面向医疗文本的智能编码映射系统，能够自动将口语化诊断描述转换为标准 ICD-10 三位码，有效提升医疗数据标准化效率。

### 🎯 核心功能

- 🔑 **API 密钥在线验证**：支持用户输入自有 API 密钥，一键验证可用性
- 📁 **CSV 文件上传**：支持批量上传诊断数据，自动识别表头
- 📋 **示例数据加载**：内置示例数据集，零门槛快速体验
- 🎯 **灵活列选择**：可视化选择诊断描述所在列
- 🤖 **多模型智能轮转**：Primary 模型（DeepSeek-V3.2、GLM-5、Qwen3）+ Secondary 模型兜底，保障服务稳定性
- 🔍 **三步编码流程**：
  - **Step 1**：LLM 初步提取 ICD 编码和标准术语
  - **Step 2**：向量检索候选编码（基于 BGE-M3 Embedding）
  - **Step 3**：Reranker 精排确认最佳匹配
- 📊 **实时进度可视化**：处理进度条、实时统计、当前模型状态一目了然
- 📦 **一键下载结果**：处理完成后自动打包 ZIP 下载，包含主结果文件、处理日志、统计摘要

---

## 🚀 在线体验

👉 **[点击访问在线 Demo](https://icd10-mapping-system-pe8ksc4dp9rvb72zu3rzwf.streamlit.app/)**

### 快速上手

1. 输入您的 API 密钥，点击「验证密钥」
2. 上传 CSV 文件（或点击「加载示例数据」体验）
3. 选择诊断描述所在的列
4. 调整置信度阈值和检索候选数（可选）
5. 点击「开始处理」，等待进度条完成
6. 点击「下载完整结果包」获取结果

---

## 🛠️ 技术架构

### 整体流程

| 步骤 | 名称 | 技术方案 | 说明 |
|:----:|------|----------|------|
| Step 1 | LLM 编码提取 | DeepSeek-V3.2 / GLM-5 / Qwen3-235B 等多模型轮转 | 直接输出 ICD 编码和标准术语，准确率高；失败自动切换模型 |
| Step 2 | 向量检索 | BGE-M3 Embedding + 余弦相似度 Top-K 召回 | LLM 无法直接命中时，在 ICD 知识库中检索候选编码，作为兜底方案 |
| Step 3 | 精排确认 | BGE-Reranker-V2-M3 相关性排序 | 对候选编码重新打分，选取最优匹配，输出置信度 |

### 技术栈

| 层级 | 技术/模型 | 用途 |
|------|-----------|------|
| 前端框架 | Streamlit | Web 界面、文件上传、进度展示、结果下载 |
| 大语言模型 | DeepSeek-V3.2、GLM-5、Qwen3-235B-A22B（Primary） | Step 1：诊断描述 → ICD 编码提取 |
| 备用模型 | DeepSeek-V4-Pro、Kimi-K2.6（Secondary） | Primary 全部失败时兜底调用 |
| Embedding | BGE-M3 | Step 2：文本向量化、相似度检索 |
| Reranker | BGE-Reranker-V2-M3 | Step 3：候选编码精排 |
| 向量计算 | NumPy | 余弦相似度计算 |
| 数据处理 | Pandas | CSV 读写、结果整理 |
| 部署平台 | Streamlit Cloud | 在线托管、公网访问 |

### 模型轮转策略

| 优先级 | 模型 | 策略 |
|:------:|------|------|
| Primary | DeepSeek-V3.2 | 默认使用，持续调用直到失败 |
| Primary | GLM-5 | 当前模型失败后依次尝试 |
| Primary | Qwen3-235B-A22B | 当前模型失败后依次尝试 |
| Secondary | DeepSeek-V4-Pro | 所有 Primary 失败后兜底 |
| Secondary | Kimi-K2.6 | 所有 Primary 失败后兜底 |
| 重置 | 返回 DeepSeek-V3.2 | Secondary 调用成功后自动切回 Primary |

---

## 📁 项目结构

```
icd10-mapping-system/
├── app.py                  # Streamlit 主程序
├── config.py               # 全局配置
├── icd_processor.py        # 核心处理引擎
├── utils/
│   ├── __init__.py
│   ├── api_client.py       # API 调用封装
│   ├── logger.py           # 日志系统
│   └── helpers.py          # 工具函数
├── data/
│   ├── icd10_data/         # ICD-10 知识库
│   └── sample/             # 示例数据
├── requirements.txt        # 依赖清单
└── README.md
```

---

## 🏃 本地运行

```bash
# 克隆仓库
git clone https://github.com/your-username/icd10-mapping-system.git
cd icd10-mapping-system

# 安装依赖
pip install -r requirements.txt

# 启动应用
streamlit run app.py
```

访问 `http://localhost:8501` 即可使用。

---

## 👥 团队成员

| 姓名 | 角色 | 贡献 |
|------|------|------|
| 黄梓宁 | 队长 / 数据处理 | 项目统筹、数据清洗 |
| 朱弈 | 前端开发 / 后端开发 | Streamlit 界面设计、agent 开发 |
| 许军 | 前端开发 | Streamlit 界面设计 |
| [成员4] | 数据处理 | 数据清洗 |
| [成员5] | 数据处理 | 数据清洗 |
| [成员6] | 数据处理 | 数据清洗 |

---

## 🏆 项目亮点

- **智能轮转策略**：多模型自动切换，保障 7×24 服务可用性
- **双重保障机制**：Step 1 基于 LLM 直接提取编码，准确率高；Step 2~3 向量检索 + 精排作为兜底方案，在 LLM 无法直接命中时自动查字典补全，确保编码覆盖率
- **用户友好**：纯 Web 界面，无需安装，上传即用

---

## 📄 许可证

本项目为复旦大学"未来智造（AI Agent）工程师"训练营参赛项目，仅供学习交流使用。

---

## 🙏 致谢

- 复旦大学团委 & 计算与智能创新学院
- 京东校园、ThinkPad、英特尔
- Streamlit 开源社区
- 所有为本项目提供支持的老师和同学

---

*Made with ❤️ by AI Agent Engineers*

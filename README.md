# AI Image Detector

图片来源与水印线索分析工具。它通过元数据、内容凭证、SynthID 水印、频谱特征和像素统计特征寻找可验证线索，辅助判断图片是否存在 AI 生成或 AI 编辑痕迹。

重要边界：本工具不是通用的“AI 图片鉴定器”。对于没有元数据、没有内容凭证、没有可检测水印的图片，尤其是 AI 生成的截图、UI、图表或设计稿，仅凭像素很难可靠判断。

## 功能

- 🔍 **元数据分析** — 检测 EXIF/PNG 中的 AI 工具签名、C2PA 标记、SD 生成参数
- 📊 **SynthID 水印检测** — 集成 reverse-SynthID V4 consensus detector，检测 Google/Gemini 相关 SynthID 水印
- 📉 **频谱分析** — FFT 频域特征检测（高频能量比、频谱斜率、周期性伪影）
- 📈 **统计分析** — 噪声分布、色彩直方图、纹理规律性等像素级特征
- 🖥️ **截图/UI 识别降权** — 识别界面截图、图表、纯色块等非自然照片，降低低噪声、无 EXIF 等弱信号权重
- 🌐 **Web 界面** — 拖拽上传，实时检测，可视化结果展示

## 快速开始

```bash
# 安装依赖
uv sync

# 启动 Web 界面
uv run python -m ai_image_detector serve

# 浏览器打开 http://127.0.0.1:8899
```

## CLI 使用

```bash
# 检测单张图片
uv run python -m ai_image_detector check image.png

# 批量检测目录
uv run python -m ai_image_detector check ./photos/

# 输出 JSON 格式
uv run python -m ai_image_detector check ./photos/ --json
```

## 检测原理

| 维度 | 检测方法 | 证据强度 |
|:-----|:---------|:--------:|
| 元数据 | EXIF/PNG 文本中的 AI 工具签名、Stable Diffusion 参数、软件字段 | 强 |
| 内容凭证 | C2PA / Content Credentials 来源记录 | 强，但需要记录存在且可信 |
| SynthID | reverse-SynthID V4 codebook 的频域相位共识检测 | 中到强，主要面向 Google/Gemini/SynthID |
| 频谱 | 高频能量比、频谱斜率、周期性伪影、棋盘格伪影 | 弱到中 |
| 统计 | 噪声均匀度、色彩熵、纹理规律性、局部一致性 | 弱 |
| 图像类型 | 截图/UI/图表/纯色图识别，用于降低自然照片假设带来的误报 | 辅助 |

结果里的“置信度”表示当前证据强度，不等于事实概率。没有检测到证据，也不代表图片一定不是 AI 生成。

## 术语说明

### C2PA

C2PA 是 Coalition for Content Provenance and Authenticity 的缩写，是一种内容来源证明标准。它可以给图片、视频、音频等文件附带一份可验证的来源记录，例如创建者、创建工具、编辑历史、是否经过 AI 生成或 AI 编辑，以及这些记录是否被篡改。

可以把 C2PA 理解为图片的“数字身份证 + 编辑履历”。如果图片带有可信 C2PA 记录，并且记录写明由某个 AI 工具生成，这是比较强的证据。

局限：

- 很多平台上传、转发、截图或压缩后会删除 C2PA 信息
- 没有 C2PA 不代表不是 AI
- 有 C2PA 也需要验证签名和来源是否可信

### EXIF

EXIF 是照片里常见的元数据。相机或手机拍照时，通常会写入相机型号、拍摄时间、镜头参数、快门、光圈、ISO、GPS、软件名称等信息。

自然照片经常有 EXIF。AI 图、截图、网页保存图通常没有完整 EXIF。但“没有 EXIF”不是 AI 证据，因为社交平台、截图、压缩工具也经常清理 EXIF。

### PNG 文本元数据

PNG 图片可以保存文本字段。Stable Diffusion、ComfyUI、Automatic1111 等工具有时会把生成参数写进去，例如 prompt、negative prompt、seed、sampler、steps、CFG scale、model name。

如果这些字段存在，通常是强 AI 生成证据。但很多图片在导出、压缩、转发后会丢失这些字段。

### SynthID

SynthID 是 Google DeepMind 的不可见水印技术。Gemini / Imagen 生成的图片可能会被嵌入肉眼不可见的信号。这个信号不依赖普通文字元数据，而是藏在图片像素和频域结构中。

当前项目集成的 reverse-SynthID 用于检测这类水印。它主要适合 Google/Gemini/SynthID 相关图片，不适合判断 OpenAI、Midjourney、Stable Diffusion 或普通截图是否 AI 生成。

### 频域 / 频谱

频域分析可以理解为把图片拆成不同方向、不同粗细的纹理波动：

- 大面积颜色变化属于低频
- 细节、边缘、噪声属于高频
- 周期性条纹、网格会在频谱里形成峰值

有些 AI 图或水印会在频谱里留下规律信号，所以项目会分析频谱。但频谱只能作为辅助证据，因为截图、UI、图表、压缩图片也可能有特殊频谱。

### 相位匹配

频谱不只有强度，还有相位。强度表示某个频率有多明显；相位表示这个频率的波形位置如何对齐。

SynthID 检测更看重相位，因为水印信号可能不是简单“更强”，而是某些频率的相位模式和参考特征一致。相位匹配度高，说明图片里的频域结构更像已知水印模式。

### Codebook

Codebook 可以理解为“水印特征字典”。reverse-SynthID 通过大量 Gemini 生成样本分析出不同尺寸、不同模型下的水印频率位置、相位模式和共识特征，并保存成 codebook。检测时，新图片会和 codebook 里的参考模式对比。

### 置信度

置信度是项目根据各种信号计算出的证据强度，不是法律意义或事实意义上的概率。

示例：

- 明确 AI 元数据：高置信证据
- SynthID 命中：中到高置信证据
- 只有低噪声、无 EXIF：低置信弱证据
- 截图/UI 类图像：低噪声、无 EXIF 通常会被降权

## 能力边界

当前项目更适合回答：

- 图片里是否有 AI 工具元数据
- 图片里是否有 C2PA / Content Credentials 线索
- 图片是否命中 Google/Gemini 相关 SynthID 水印
- 图片是否存在一些弱像素统计异常

当前项目不适合高置信回答：

- 这张截图是不是 AI 生成
- 这张 UI 设计稿是不是 `gpt-image-2` 生成
- 没有元数据和水印的图片是否一定不是 AI
- 所有平台、所有模型生成图片的统一鉴定

对于 `gpt-image-2` 这类模型生成的截图或 UI 图，如果没有 OpenAI 侧内容凭证、平台元数据、生成记录或其他 provenance 信号，单靠像素很难可靠识别。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **图像处理**: NumPy, SciPy, OpenCV, PyWavelets
- **前端**: 原生 HTML/CSS/JS，暗色主题

## 第三方组件

本项目集成了 reverse-SynthID 的检测思路、V4 consensus detector 和 codebook 资源。

来源：reverse-SynthID by Alosh Denny — github.com/aloshdenny/reverse-SynthID

许可证：reverse-SynthID Research License v1.0。该许可证限制为非商业使用，并要求署名。商业使用需要单独授权。

## 免责声明

本工具仅供研究和参考使用，检测结果不构成最终判定。输出应理解为“发现了哪些来源或水印线索”，而不是对图片真实来源的绝对判决。

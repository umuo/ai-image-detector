# AI 图片检测可靠性说明

这份文档整理当前市面上判断图片是否由 AI 生成或 AI 编辑的主要方案，以及它们适合解决的问题和不适合承担的结论。

核心结论：

- 没有一种通用检测方法可以稳定判断所有图片是否由 AI 生成。
- 最可靠的证据来自可验证来源记录和厂商水印，而不是单纯像素分类。
- 检测结果应该表达为“证据等级”和“不确定性”，不要表达为绝对判决。
- “未发现证据”不等于“不是 AI 图片”。

## 可靠性排序

| 等级 | 方法 | 证据强度 | 适合回答 | 主要局限 |
|:--|:--|:--|:--|:--|
| 1 | C2PA / Content Credentials | 强 | 文件是否带有可信来源记录，是否声明由某工具生成或编辑 | 元数据可能被平台、截图、转存移除；没有 C2PA 不代表不是 AI |
| 2 | 厂商水印 | 强 | 是否命中某厂商或某生态的水印，例如 SynthID | 覆盖范围有限；没命中不代表不是 AI |
| 3 | 商业检测 API | 中 | 批量审核、风控初筛、平台治理 | 概率输出，依赖训练集，面对新模型和后处理会退化 |
| 4 | 图像取证分析 | 弱到中 | 是否存在异常压缩、噪声、频谱、统计特征 | 容易受截图、压缩、裁剪、修图、UI 图影响 |
| 5 | 人工视觉判断 | 弱 | 辅助发现明显伪影或上下文矛盾 | 现代生成模型越来越难靠肉眼稳定识别 |

## 1. C2PA / Content Credentials

C2PA 是内容来源证明标准，可以把图片的来源、创建工具、编辑历史、AI 生成或 AI 编辑声明等信息写入可验证的内容凭证中。

如果图片带有可信 C2PA 记录，并且签名验证通过，同时记录明确声明由某个 AI 工具生成，这是强证据。

适合输出：

- 检测到可信 Content Credentials
- 内容凭证声明该图片由某工具生成或编辑
- 内容凭证签名有效

不适合输出：

- 未检测到 C2PA，所以不是 AI 图片
- 只要有 C2PA 就一定真实可信

原因是 C2PA 可能在截图、社交平台转发、压缩、格式转换时丢失。没有 C2PA，只能说明没有检测到这类来源凭证。

## 2. 厂商水印

厂商水印是目前比普通像素分类更强的 AI 生成证据。典型例子是 Google DeepMind 的 SynthID。它把不可见数字水印嵌入 AI 生成图片、视频、音频或文本中，检测器再识别这些水印。

对于 SynthID，合理表述是：

- 命中 SynthID：强证据表明图片可能由支持 SynthID 的 Google AI 相关系统生成或编辑。
- 未命中 SynthID：只代表未发现 SynthID 水印，不能排除图片由其他 AI 系统生成。

不要把 SynthID 当成通用 AI 图片检测器。它主要回答“是否有这类水印”，不是回答“所有模型生成的图片都能否识别”。

## 3. 商业检测 API

市面上常见的商业或平台型检测服务包括：

- Hive AI-Generated Image and Video Detection
- Sightengine AI Image Detection
- Reality Defender
- Sensity
- AI or Not
- TrueMedia

这些服务通常使用模型集合、图像取证、深度伪造检测、元数据分析等方法，适合做内容审核和风险初筛。

工程上应该把它们看成一个概率信号，而不是最终裁决。更稳妥的设计是同时记录：

- 检测供应商
- 检测时间
- 模型版本或接口版本
- 原始分数
- 阈值
- 是否触发人工复核

不建议把某个 API 的结果直接写成“该图片一定是 AI 生成”。

## 4. 图像取证分析

图像取证通常包括：

- EXIF / PNG 文本字段
- 软件字段和生成参数
- 压缩历史
- 噪声分布
- PRNU 相机指纹
- 频谱特征
- 色彩直方图
- 纹理规律性
- 局部一致性

这类方法对原始文件更有价值。图片经过社交平台压缩、截图、裁剪、滤镜、转码后，取证信号会变弱甚至反转。

常见误判来源：

- 截图和 UI 图通常没有相机 EXIF
- 设计稿、图表、插画可能有低噪声和大面积纯色
- 重度美颜、降噪、超分、修复会改变自然照片特征
- 社交平台压缩会破坏高频和噪声特征
- AI 局部编辑可能只影响图片一小块区域

因此图像取证更适合解释“发现了什么异常”，不适合单独得出“这是 AI 图”的结论。

## 5. 人工和 OSINT 交叉验证

在新闻、法律、舆情、风控场景中，人工和上下文验证仍然重要。

可以结合：

- 反向搜图
- 最早发布时间
- 发布账号可信度
- 原始文件来源
- 拍摄地点和天气
- 阴影、反射、透视、物理一致性
- 是否存在同场景其他照片或视频
- 是否能找到原始相机文件

人工判断不应替代技术检测，但可以发现纯模型分数无法覆盖的上下文问题。

## 推荐的产品结论分级

建议项目输出证据等级，而不是输出二元判断。

| 结论等级 | 建议文案 | 触发条件 |
|:--|:--|:--|
| 高置信 AI 线索 | 检测到强 AI 来源证据 | C2PA 声明 AI 生成、厂商水印命中、明确生成参数存在 |
| 中置信 AI 线索 | 多个弱信号共同指向 AI 生成或编辑 | 商业 API 高分，并伴随频谱、统计、元数据异常 |
| 低置信 AI 线索 | 存在弱异常，但不足以定性 | 只有像素统计或频谱异常 |
| 未发现明确 AI 线索 | 当前文件中未发现可验证 AI 证据 | 无 C2PA、无水印、无元数据，仅表示证据不足 |
| 无法判断 | 文件条件不支持可靠检测 | 截图、严重压缩、小尺寸、二次转发、局部裁剪 |

## 推荐的工程架构

一个相对稳健的 AI 图片检测流程：

1. 文件完整性和格式解析
2. C2PA / Content Credentials 验证
3. EXIF、PNG 文本、XMP、IPTC 元数据分析
4. 厂商水印检测，例如 SynthID
5. 图像类型识别，区分自然照片、截图、UI、图表、插画
6. 图像取证分析，包括频谱、噪声、压缩、纹理
7. 可选商业 API 交叉检测
8. 聚合证据，输出证据等级和解释
9. 高风险场景进入人工复核

聚合时建议采用证据权重，而不是简单平均分。强证据可以直接提高结论等级，弱证据只能辅助，不应单独触发高置信结论。

## 推荐文案

可以使用：

- 检测到可信内容凭证，凭证声明该图片由 AI 工具生成。
- 检测到 SynthID 水印，说明该图片可能由支持 SynthID 的系统生成或编辑。
- 未发现 SynthID 水印，但不能排除其他 AI 系统生成。
- 当前仅发现弱像素异常，建议结合来源、元数据和人工复核。
- 该图片疑似截图或二次压缩图，像素级检测可靠性较低。

避免使用：

- 这张图一定是 AI 生成。
- 这张图一定不是 AI 生成。
- 未检测到水印，所以不是 AI。
- 该图由某厂商生成，但没有可验证凭证或水印证据。
- 仅凭像素分数进行法律、学术、版权或平台处罚结论。

## 关于伪造和误归因

检测系统应防止被用于错误归因或嫁祸。

需要特别注意：

- EXIF 和普通文本元数据容易伪造。
- 普通像素检测器可能被对抗样本或后处理影响。
- 厂商水印通常更难伪造，但检测结果仍应表达为概率或证据。
- 涉及处罚、版权、法律、舆情结论时，必须保留原始文件、检测日志和人工复核记录。

产品上不要只给“AI / 非 AI”的单一标签。更好的方式是展示证据来源、强弱和不确定性。

## 对本项目的落地建议

本项目已经覆盖：

- 元数据分析
- C2PA / Content Credentials 线索识别
- SynthID 水印检测
- 频谱分析
- 像素统计分析
- 截图 / UI 类图像降权

后续可以增强：

- 更完整的 C2PA 签名验证
- 检测结果证据链导出
- 商业 API 可选插件
- 原始文件哈希和检测日志记录
- 高风险结果的人工复核状态
- 针对截图、UI、图表、插画的独立结论模板

## 参考资料

- C2PA: https://c2pa.org/
- Content Credentials Verify: https://contentcredentials.org/verify
- OpenAI C2PA in ChatGPT Images: https://help.openai.com/en/articles/8912793-c2pa-in-chatgpt-images
- Google DeepMind SynthID: https://deepmind.google/models/synthid/
- Google SynthID Detector announcement: https://blog.google/innovation-and-ai/products/google-synthid-ai-content-detector/
- Hive AI Image and Video Detection: https://docs.thehive.ai/docs/ai-image-and-video-detection
- Sightengine AI Generated Image Detection: https://www-cf.sightengine.com/docs/ai-generated-image-detection
- Reality Defender: https://www.realitydefender.com/
- Sensity API: https://docs.sensity.ai/
- AI or Not API: https://docs.aiornot.com/
- TrueMedia: https://www.truemedia.org/
- NIST synthetic content transparency report: https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=959123

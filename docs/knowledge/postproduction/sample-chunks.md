# 后期剪辑知识库｜公开样例块

来源：GitHub 公开脱敏样例。当前公开仓库只展示后期处理规则片段，不发布私有供应商配置、素材存储路径或 API 凭证。

> 以下内容为脱敏样例，用于展示知识块粒度和调用方式，不是完整生产配置。

## chunk postproduction-001

| 字段 | 内容 |
| --- | --- |
| role | postproduction |
| stage | stage-4 |
| content_type | 信息流广告 / 高端 TVC |
| objective | 接收成片并生成交付版 |

后期阶段默认继承前序确认的产品、Hook、脚本、分镜和视频结果，不重新改写创意方向。处理重点是成片整理、字幕、配乐、音量、清晰度和可下载交付。

## chunk postproduction-002

| 字段 | 内容 |
| --- | --- |
| role | postproduction |
| stage | stage-4 |
| content_type | 信息流广告 |
| objective | 保持平台展示尺寸和可播放性 |

信息流视频默认保持竖版比例和产品可见性，避免二次裁切导致手机、瓶身、Logo 或关键卖点被遮挡。公开 Demo 只使用固定视频 URL，不调用真实剪辑、配乐或画质增强接口。

## chunk postproduction-003

| 字段 | 内容 |
| --- | --- |
| role | postproduction |
| stage | stage-4 |
| content_type | 高端 TVC |
| objective | 保留 16:9 原比例交付 |

TVC 后期默认保留 16:9 画面比例，不拉伸、不裁切。字幕、配乐和高清导出只作为交付层处理，不改变摄影摄像阶段确认过的构图和产品主体位置。

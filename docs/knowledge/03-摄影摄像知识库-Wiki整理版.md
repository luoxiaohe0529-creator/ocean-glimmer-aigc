# 摄影摄像知识库

版本：V3.0  
阶段：Stage 3  
用途：固定摄影模板库。把 Stage 2 的逐镜分镜翻译成可生成、可拍摄的视频提示词和连续性约束。

## 一、职责与边界

本知识库只决定“这个镜头怎样拍、怎样生成、怎样保持一致”。不重新选择 Hook，不修改 Mood Board、Slogan、镜头顺序、镜头叙事任务或 `template_group_id`。

优先级：产品事实与甲方限制 > Stage 1 创意板 > Stage 2 分镜 > 精确摄影模板 > 品类补丁 > 模型补全。

## 二、固定路由

```text
live-general-v3 -> 真人口播摄影模板
review-general-v3 -> 好物推荐摄影模板
tvc-brand-v3 -> 电影叙事摄影
tvc-social-fastcut-v3 -> 快剪视觉摄影
tvc-material-v3 -> 微距材质摄影
```

Stage 3 必须按 `template_group_id` 精确读取一张摄影母模板。不得用一个通用“高级电影感”提示词覆盖所有类型。

## 三、统一输入契约

必须接收：Stage 1 选中创意板、Stage 2 完整逐镜分镜、产品图、人物身份图、分镜参考图、产品允许展示部位、必须出现元素、禁止事项、内容类型、品类、语言、画幅、总时长和前端选择的分辨率。

分辨率必须使用前端值 `480p / 720p / 1080p`，不得在知识库或节点中写死。

## 四、真人口播摄影模板

CARD_START
card_id: camera-live-general-v3
card_type: camera_master_template
template_group_id: live-general-v3
content_type: 真人口播带货
content_subtype: 真人口播带货
product_category: all
priority: 100
tags: 真人；口播；表情；手部；收音；自然光；实操
match_rule: template_group_id等于live-general-v3。
template_body: 你是一位擅长竖屏真人成交内容的摄影指导。人物眼神、表情、口型和手部实操优先，产品信息必须清楚但不过度商业摆拍。使用稳定中近景作为口播主镜头，用近景和微距补充证明动作。光线自然柔和，肤色真实，背景整洁且与使用场景有关。运镜只在人物动作或产品证明需要时发生。
prompt_rule: 每个视频提示词写清人物身份、动作、口型状态、产品、场景、景别、光线、摄像机运动、时长、9:16和连续性。
negative_rules: no subtitles；no captions；no text overlay；no watermark；no logo；no UI；no beauty-filter face drift；no extra fingers；no product drift；no lip-sync mismatch
CARD_END

## 五、好物推荐摄影模板

CARD_START
card_id: camera-review-general-v3
card_type: camera_master_template
template_group_id: review-general-v3
content_type: 好物推荐
content_subtype: 好物推荐
product_category: all
priority: 100
tags: 好物；证据；细节；操作；比较；结果；生活化
match_rule: template_group_id等于review-general-v3。
template_body: 你是一位擅长生活化产品测评与好物展示的摄影指导。每个镜头只证明一个具体结论。建立镜头交代使用场景，俯拍或侧俯拍呈现操作流程，微距呈现材质与细节，中近景呈现人物反应和结果。比较镜头必须保持相同光线、角度、距离和背景，避免视觉作弊。
prompt_rule: 每个提示词必须包含证据目标、产品动作、可见结果、景别、机位、光线、运镜、连续性和无文字规则。
negative_rules: no fake measurement；no unsupported before-after；no subtitles；no logo；no watermark；no UI；no product shape drift；no color drift
CARD_END

## 六、高端 TVC 摄影模板

### 6.1 电影叙事摄影

CARD_START
card_id: camera-tvc-cinematic-v3
card_type: camera_master_template
template_group_id: tvc-brand-v3
content_type: 高端TVC
content_subtype: 品牌叙事TVC
product_category: all
priority: 110
tags: 电影；空间；人物关系；自然光；运动；声音桥；连续性
match_rule: template_group_id等于tvc-brand-v3。
template_body: 你是一位擅长电影化商业短片的摄影指导。摄影服务人物关系和情绪曲线。建立镜头交代空间，稳定跟拍保留人物呼吸，近景捕捉关系变化，特写强调关键动作。光线随叙事从压抑到开阔、从冷到暖或按 Mood Board 规定演化。运镜必须有动机：跟随、靠近、离开、揭示或回望。产品始终参与人物动作，并与场景光线保持真实接触。
prompt_rule: 英文提示词按主体动作、场景空间、时间光线、颜色材质、景别构图、运镜、物理运动、产品锁、人物锁、画幅时长、负面规则排列。
negative_rules: no empty landscape montage；no random drone shot；no subtitles；no title card；no logo；no watermark；no UI；no identity drift；no product drift
CARD_END

### 6.2 快剪视觉摄影

CARD_START
card_id: camera-tvc-fastcut-v3
card_type: camera_master_template
template_group_id: tvc-social-fastcut-v3
content_type: 高端TVC
content_subtype: 社媒氛围快剪TVC
product_category: all
priority: 120
tags: 快剪；微距；极速推轨；甩镜；匹配转场；高速摄影；高截图率；竖屏
match_rule: template_group_id等于tvc-social-fastcut-v3。
template_body: 你是一位擅长高截图率竖屏商业短片的摄影指导。严格保留 Stage 2 每个镜头的叙事任务和时间。使用微距、极近特写、快速推轨、快速横移、甩镜、手持跟拍、稳定器跟拍、高速摄影、相似体转场、叠化和声音桥建立节奏。每个镜头只有一个视觉焦点。快剪镜头通常0.8至1.5秒，画面必须在第一帧就明确主体。产品颜色、比例、材质和允许展示部位全程锁定。水、玻璃、光斑、织物、花瓣等风格元素只能服务产品，不得遮挡或改造产品。
prompt_rule: 每个英文提示词必须独立完整，明确shot size、subject、action、product exposure、scene、lighting、material、camera movement、speed、9:16、duration、identity lock和no-text block。不得把“高级、梦幻、清凉”作为唯一描述，必须转成可见光线、颜色、材质和动作。
negative_rules: no subtitles；no captions；no title cards；no logos；no watermarks；no UI；no screen text；no rendered words；no extra electronics；no product shape drift；no color drift；no random product flipping；no unsupported waterproof or drop test
CARD_END

### 6.3 微距材质摄影

CARD_START
card_id: camera-tvc-macro-material-v3
card_type: camera_master_template
template_group_id: tvc-material-v3
content_type: 高端TVC
content_subtype: 产品材质视觉TVC
product_category: all
priority: 110
tags: 微距；材质；高光；液体；颗粒；玻璃；金属；形状匹配
match_rule: template_group_id等于tvc-material-v3。
template_body: 你是一位擅长高端产品微距和材质实验的摄影指导。使用微距或探针镜头表现表面细节，以硬边高光、柔光带、轮廓光和偏振控制区分玻璃、金属、磨砂、膏体、粉体、织物与液体。景深必须服务材质识别，焦点从类比物准确转移到产品识别点。相似体转场必须匹配形状、颜色、方向和速度。产品结构、文字位置和比例不得变化。
prompt_rule: 提示词必须写清材质物理状态、光源尺寸与方向、焦点、景深、镜头运动、转场匹配点、产品锁和负面规则。
negative_rules: no abstract effect covering product；no impossible liquid physics；no product deformation；no color drift；no added parts；no subtitles；no logos；no watermarks；no UI
CARD_END

## 七、品类摄影补丁

CARD_START
card_id: camera-category-phone-v3
card_type: category_patch
product_category: 手机与数码
priority: 60
template_body: 产品参考图是最高身份来源。锁定机身比例、背板颜色、边框、允许展示区域和握持方式。优先使用背板反光、边缘光、自然握持和环境材质呼应。若甲方禁止正面，所有提示词明确 back panel or side silhouette only, never show front screen or UI。
negative_rules: no front screen；no UI；no camera-module invention；no extra electronics；no product deformation；no unsupported waterproof；no unsupported drop test
CARD_END

CARD_START
card_id: camera-category-beauty-v3
card_type: category_patch
product_category: 美妆个护
priority: 60
template_body: 锁定包装、色号、膏体或液体质地、人物肤色和妆效。微距表现涂抹边缘、光泽、粉雾、丝滑或镜面状态；人物镜头保持真实皮肤纹理。
negative_rules: no skin-tone change；no instant medical result；no package drift；no shade drift；no deformed applicator；no excessive beauty filter
CARD_END

CARD_START
card_id: camera-category-fashion-v3
card_type: category_patch
product_category: 服饰与配饰
priority: 60
template_body: 锁定版型、颜色、图案、面料和配饰。使用侧逆光、运动模糊和局部慢动作表现面料动态，同时用全身镜头校验整体轮廓。
negative_rules: no garment morphing；no pattern drift；no color drift；no extra accessories；no body distortion
CARD_END

CARD_START
card_id: camera-category-food-v3
card_type: category_patch
product_category: 食品饮料
priority: 60
template_body: 锁定包装、容器、食品颜色、温度和余量。用高速摄影表现气泡、飞溅和碎裂，用微距表现蒸汽、酥脆、拉丝或流动，但保持真实物理状态。
negative_rules: no ingredient invention；no impossible food physics；no package drift；no unhygienic handling；no artificial color change
CARD_END

## 八、参考图分配规则

- 产品特写：只带产品身份图和必要的局部参考图。
- 人物镜头：产品身份图 + 人物身份图。
- 复杂构图：产品身份图 + 对应分镜图；Mood Board 仅作风格参考。
- 禁止把全部图片无差别塞进每个镜头。
- 优先级：产品身份 > 人物身份 > Stage 2 分镜 > Mood Board > 纯风格参考。

## 九、统一视频提示词公式

```text
[Shot size and composition].
[Subject identity] [specific visible action] with [exact product exposure].
[Scene and spatial relationship].
[Time, lighting direction, color palette and material behavior].
[Camera position and camera movement] at [motion speed].
[Continuity anchors].
Vertical 9:16, [shot duration], output resolution from frontend: [resolution].
No subtitles, no captions, no title cards, no logos, no watermarks,
no UI, no screen text, no rendered words, no identity drift,
no product shape drift, no product color drift.
```

抽象词必须被翻译：

```text
清凉 -> 低饱和冷色、透明边缘光、凝露、水面高光、轻快动作
浪漫 -> 柔和逆光、粉蓝或暖粉层次、轻风、花瓣或织物的真实运动
高级 -> 控制高光、克制配色、干净构图、明确材质、稳定产品比例
梦幻 -> 薄雾、柔焦背景、体积光或反射层次，但产品识别点保持清晰
松弛 -> 自然呼吸、非正视镜头、动作有前因后果、手持或稳定器轻跟随
```

## 十、Stage 3 固定摄影命令

```text
你是［命中的摄影模板角色］。

严格继承 Stage 1 的 template_group_id 和 Stage 2 的镜头顺序、时间、叙事任务、动作、产品露出与连续性。不得重新写故事，不得合并或调换镜头。

为每个镜头生成：中文摄影说明、英文video_prompt、negative_prompt、输入参考图分配、continuity_in、continuity_out。英文提示词必须具体描述主体、动作、产品、场景、光线、材质、景别、机位、运镜、速度、时长、9:16和前端分辨率。

所有镜头禁止字幕、标题卡、Logo、水印、UI、屏幕文字和任何渲染文字。没有事实依据时禁止浸泡、跌落、功效对比和结构变化。
```

## 十一、结构化输出

```json
{
  "template_group_id": "tvc-social-fastcut-v3",
  "camera_template_id": "camera-tvc-fastcut-v3",
  "resolution": "480p",
  "aspect_ratio": "9:16",
  "no_subtitles": true,
  "continuity_bible": {
    "product_lock": {},
    "character_lock": {},
    "scene_lock": {},
    "forbidden": []
  },
  "storyboard": [
    {
      "shot_id": "S01",
      "source_shot_id": "S01",
      "start": 0,
      "end": 1,
      "visual_zh": "",
      "camera_zh": "",
      "video_prompt": "",
      "negative_prompt": "",
      "reference_images": [],
      "continuity_in": [],
      "continuity_out": [],
      "subtitle": ""
    }
  ],
  "provider_route": {}
}
```

## 十二、交付校验

- `template_group_id` 必须与 Stage 1、Stage 2 完全一致。
- `source_shot_id` 必须存在，顺序和时间必须与 Stage 2 一致。
- 所有镜头总时长必须等于成片时长。
- 每个提示词必须包含产品身份锁和无文字规则。
- `subtitle` 和 `subtitle_zh` 始终为空。
- `resolution` 必须来自前端，默认 480p，但允许用户选择 720p 或 1080p。
- 手机禁止正面时，不得出现自拍、屏幕闪光、UI或正面显示。
- 没有防水或抗摔事实时，不得让产品浸泡、危险跌落或以此证明性能。

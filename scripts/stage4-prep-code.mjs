export function stage4PrepCode() {
  return `const b=$input.first().json.body||$input.first().json;
const pid=b.video_task_id||b.product_record_id||"rec_"+Date.now();
const product=b.product_brief||{};
const name=product["产品名称"]||product.product_name||"产品";
const selling=product["核心卖点"]||product.selling_points||"";
const sell=Array.isArray(selling)?selling.join(" · "):String(selling);
const duration=Number(b.duration)||15;
const requestedResolution=String(b.resolution||"480p").trim().toLowerCase();
const allowedResolutions=["480p","720p","1080p"];
const resolution=allowedResolutions.includes(requestedResolution)?requestedResolution:"480p";
const filterValues=b.filter_values||b.filterValues||{};
const adType=filterValues.ad_type||b.ad_type||"由 AI 决定";
const voiceType=filterValues.voice_type||b.voice_type||"真人口播";
const contentType=b.content_type||"真人口播带货";
const creativeTags=Object.entries(filterValues).filter(([key,value])=>value&&!["ad_type","voice_type"].includes(key)).map(([,value])=>String(value)).join(" · ");
const creativePlan=b.creative_plan||b.selected_plan||{};
const directorInstruction=b.director_instruction||creativePlan.director_guidance||"";
const planDirection=[creativePlan.core_hook||creativePlan.hook||"",creativePlan.slogan||"",creativePlan.mood_board||"",creativePlan.opening_method||"",creativePlan.rhythm_skeleton||"",Array.isArray(creativePlan.visual_codes)?creativePlan.visual_codes.join("、"):creativePlan.visual_codes||""].filter(Boolean).join("；");
const selectedMoodBoard=b.selected_mood_board||creativePlan.selected_mood_board||{};
const moodValue=value=>Array.isArray(value)?value.filter(Boolean).join("、"):value&&typeof value==="object"?Object.values(value).filter(Boolean).join("、"):String(value||"");
const moodDirection=[
  "名称："+moodValue(selectedMoodBoard.name||creativePlan.mood_board),
  "情绪："+moodValue(selectedMoodBoard.emotion_direction||creativePlan.emotion_direction),
  "色彩："+moodValue(selectedMoodBoard.palette),
  "光线："+moodValue(selectedMoodBoard.lighting),
  "材质："+moodValue(selectedMoodBoard.materials),
  "场景："+moodValue(selectedMoodBoard.scene_grammar),
  "人物："+moodValue(selectedMoodBoard.character_state),
  "镜头语言："+moodValue(selectedMoodBoard.camera_language),
  "负面约束："+moodValue(selectedMoodBoard.negative_rules)
].filter(value=>!value.endsWith("：")).join("；");
const filterSummary=JSON.stringify(filterValues);
let storyboard=b.storyboard;
if(typeof storyboard==="string"){try{storyboard=JSON.parse(storyboard);}catch(error){throw new Error("storyboard 不是有效 JSON");}}
let storyboardSegments=b.segments;
if(typeof storyboardSegments==="string"){try{storyboardSegments=JSON.parse(storyboardSegments);}catch(error){storyboardSegments=[];}}
if(!Array.isArray(storyboardSegments))storyboardSegments=[];
if(!Array.isArray(storyboard))storyboard=[];
if(!storyboard.length&&storyboardSegments.length)storyboard=storyboardSegments.reduce((all,segment)=>all.concat(Array.isArray(segment.storyboard)?segment.storyboard:[]),[]);
if(!storyboard.length)throw new Error("缺少导演分镜，不能直接根据脚本文本重新创作");
const sourceScriptSegments=Array.isArray(b.script_segments)?b.script_segments:[];
const textOverlayKeys=new Set(["subtitle","subtitle_zh","subtitles","caption","captions","on_screen_text","text_overlay","text_overlays","title_card","supers"]);
const withoutTextOverlays=value=>{
  if(Array.isArray(value))return value.map(withoutTextOverlays);
  if(!value||typeof value!=="object")return value;
  return Object.fromEntries(Object.entries(value).filter(([key])=>!textOverlayKeys.has(String(key).toLowerCase())).map(([key,item])=>[key,withoutTextOverlays(item)]));
};
const sourceScriptSegmentsForVideo=withoutTextOverlays(sourceScriptSegments);
const validStoryboardSegments=storyboardSegments.filter(segment=>{
  if(!segment||!Array.isArray(segment.storyboard)||!segment.storyboard.length)return false;
  const start=Number(segment.start);
  const end=Number(segment.end);
  return Number.isFinite(start)&&Number.isFinite(end)&&end>start&&end-start<=15;
});
const totalSegments=Math.max(1,Math.ceil(duration/15),validStoryboardSegments.length||0);
const parseStart=value=>{const match=String(value||"").match(/(\\d+(?:\\.\\d+)?)/);return match?Number(match[1]):0;};
const parseEnd=value=>{const match=String(value||"").match(/[-~至](\\d+(?:\\.\\d+)?)/);return match?Number(match[1]):parseStart(value);};
const shotStart=shot=>Number.isFinite(Number(shot.start))?Number(shot.start):parseStart(shot.time||shot.timestamp);
const shotEnd=shot=>Number.isFinite(Number(shot.end))?Number(shot.end):parseEnd(shot.time||shot.timestamp);
const shotText=(shot,index)=>{
  const shotWindow=shot.time||shot.timestamp||((shot.start||0)+"-"+(shot.end||"")+"s");
  const values=[
    "镜头"+(index+1)+"（"+shotWindow+"）",
    "画面："+(shot.visual||shot.scene_description||shot.description||""),
    "动作："+(shot.action||""),
    "运镜："+(shot.camera_movement||shot.camera||""),
    "人物："+(shot.performance||shot.character_action||""),
    "产品露出："+(shot.product_exposure||""),
    "光线材质："+(shot.lighting||shot.materials||""),
    "声音："+(shot.music_sfx||""),
    "口播："+(shot.dialogue||shot.voiceover||""),
    "视频提示词："+(shot.video_prompt||shot.seedance_prompt||""),
    "连续性："+(Array.isArray(shot.continuity_anchors)?shot.continuity_anchors.join("、"):shot.continuity_anchors||"")
  ];
  return values.filter(value=>!value.endsWith("：")).join("；");
};
const shotsForSegment=index=>{
  const segment=validStoryboardSegments[index];
  if(segment&&Array.isArray(segment.storyboard)&&segment.storyboard.length)return segment.storyboard;
  const start=index*15;
  const end=Math.min(duration,(index+1)*15);
  if(totalSegments===1)return storyboard;
  return storyboard.filter(shot=>shotStart(shot)<end&&shotEnd(shot)>start);
};
const refs=[b.product_image_url,...(Array.isArray(b.product_images)?b.product_images.map(image=>image&&image.url||image):[])].filter(Boolean).slice(0,5);
const useVeo=/^(英文|english|en)$/i.test(String(b.language||"中文").trim());
return Array.from({length:totalSegments},(_,index)=>{
  const shots=shotsForSegment(index);
  const segmentStart=Number(validStoryboardSegments[index]?.start);
  const segmentEnd=Number(validStoryboardSegments[index]?.end);
  const actualStart=Number.isFinite(segmentStart)?segmentStart:index*15;
  const actualEnd=Number.isFinite(segmentEnd)?segmentEnd:Math.min(duration,(index+1)*15);
  const shotsForVideo=shots.map(withoutTextOverlays);
  const exactShotPlan=shotsForVideo.map((shot,shotIndex)=>shotText(shot,shotIndex)).join("\\n");
  const prompt=[
    "9:16 竖屏商业视频，第"+(index+1)+"/"+totalSegments+"段，时长"+(actualEnd-actualStart)+"秒。",
    "这是已完成的导演分镜执行任务，不是重新创意。必须按镜头顺序逐条执行，不得删除、合并、改写或补造镜头。",
    "产品："+name+"。核心卖点："+sell+"。内容类型："+contentType+"。广告形式："+adType+"。声音："+voiceType+"。分辨率："+resolution+"。",
    "筛选器结果："+filterSummary+"。创意方向："+(creativeTags||"由已选方案决定")+"。",
    "已选创意方案："+(planDirection||"按上游创意方案执行")+"。Mood Board 视觉执行约束："+(moodDirection||"按上游 Mood Board 执行")+"。导演指导："+directorInstruction+"。",
    "Stage 2 结构化脚本段（已移除所有字幕字段）："+JSON.stringify(sourceScriptSegmentsForVideo)+"。",
    "本段逐镜执行清单：\\n"+exactShotPlan,
    "Mood Board 是本段的主视觉，不得退化为普通产品展示：必须把它的主色、光线、材质、人物状态和镜头节奏落实到对应镜头。Slogan 只作为创意方向，不得渲染成画面文字。",
    "如果上游脚本与无字幕规则冲突，以无字幕规则为最高优先级：脚本中出现的字幕、标题、品牌名、Slogan 文字、屏幕文字、UI 或界面均改为纯视觉动作，不得生成任何文字画面。",
    "成片禁止任何字幕、字幕条、标题卡、品牌字样、Slogan 文字、UI、屏幕文字、Logo 和水印；可以保留口播与环境音，但绝不能把口播转成文字。",
    "保持产品外观、包装、色彩、人物、服装、场景和光线连续；不要出现未被上游允许的品牌标识、道具或功能。"
  ].join("\\n");
  const content=[{type:"text",text:prompt}];
  for(const url of refs)content.push({type:"image_url",image_url:{url},role:"reference_image"});
  return {json:{...b,video_task_id:pid,video_prompt:prompt,seedance_content:content,ref_images:refs,segment_index:index+1,total_segments:totalSegments,duration:actualEnd-actualStart,resolution,no_subtitles:true,source_shots:shotsForVideo,source_script_segments:sourceScriptSegmentsForVideo,segment_start:actualStart,segment_end:actualEnd,use_veo:useVeo,provider:useVeo?"kie.ai/veo3.1":"seedance-official"}};
});`;
}

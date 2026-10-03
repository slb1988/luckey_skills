# 动画媒体交付（标准流程 Step 9 / 9.5）

动画/视频交付前必读。三方向批准门和导演稿门仍以 [SKILL.md](../SKILL.md) 为准；命令从 skill 根目录运行，只有对应的云能力已获显式授权才可调用。

9. **（默认）导出视频 · 必带 SFX + BGM**：动画 HTML 的**默认交付形态是带音频的 MP4**，不是纯画面。无声版本等于半成品——用户潜意识感知「画在动但没声音响应」，廉价感的根源就在这里。流水线：
   - **新动画项目默认 HyperFrames 后端**：`npm run check`（五门审计，暗色电影风 `--no-contrast`）→ `npx hyperframes render --fps 60` → `scripts/verify-video.sh` 产物硬校验。选型边界与老 demo 适配器配方见 `hyperframes-backend.md`；弱 runtime/单文件交付/纯交互演示仍走下面的自研管线
   - `scripts/render-video.js` 录 25fps 纯画面 MP4（只是中间产物，**不是成品**）
   - 需要**真 60fps / 确定性 / B站作品集交付**且动画走 Stage 时钟时，改用 `scripts/render-video-seek.js --fps=60`（逐帧 seek，免插帧、无黑帧，详见 `video-export.md`）
   - `scripts/convert-formats.sh` 派生 60fps MP4 + palette 优化 GIF（视平台需要）
   - `scripts/add-music.sh` 加 BGM（6 首场景化配乐：tech/ad/educational/tutorial + alt 变体）
   - SFX 按 `audio-design-rules.md` 设计 cue 清单（时间轴 + 音效类型），用 `../assets/sfx/<category>/*.mp3` 37 个预制资源，按配方 A/B/C/D 选密度（发布 hero ≈ 6个/10s，工具演示 ≈ 0-2个/10s）
   - **BGM + SFX 双轨制必须同时做**——只做 BGM 是 ⅓ 分完成度；SFX 占高频、BGM 占低频，频段隔离见 audio-design-rules.md 的 ffmpeg 模板
   - 交付前 `ffprobe -select_streams a` 确认有 audio stream，没有则不是成品
   - **（终渲后）AI看片评审**（可选云能力，自备key+显式确认，见 ../SECURITY.md）：`uv run scripts/cloud/ai-review-video.py --video <成片> --context 导演稿.md --yes` 出结构化报告（黑帧/死段/hero贯穿/过渡类型/音效空打），流程与局限见 `ai-video-review.md`；无key时用 `scripts/verify-video.sh` 截帧人工看
   - **跳过音频的条件**：用户明确说「不要音频」「纯画面」「我要自己配音」——否则默认带。
   - 参考完整流程见 `video-export.md` + `audio-design-rules.md` + `sfx-library.md`。
9.5. **（带解说时走这条）解说驱动动画 · L2 长概念视频**：用户要做「5-20 分钟解释一个概念」、「带配音的教程」、「长篇科普视频」时——**不要先做动画再配音**，那会让画面节奏跟解说对不上。改走 `voiceover-pipeline.md` 的解说驱动流程：
   - **写解说稿**（markdown，`## scene-id` 分段，`[[cue:xx]]` 标关键句）→ 解说稿是源代码，节奏靠它撑
   - **跑 narrate-pipeline.mjs**（豆包 TTS · `.env` 配置音色）→ 输出 voiceover.mp3 + timeline.json（cue 时间是真实测出来的，不是按字符估算）
   - **🛑 设计动画前先答铁律 3 条**：(1) hero element 是什么？(2) 它跨 7 段怎么 morph？(3) 任意一帧画面有运动吗？答不上不要写代码
   - **写动画 HTML**：用 `../assets/narration_stage.jsx`（NarrationStage + Scene + Cue + useNarration + useSceneFade + **Subtitles**）→ hero 直接放 `<NarrationStage>` 子级，不进 Scene；`<Subtitles />` 默认带（B 站风·深墨字+白光晕，按 timeline.chunks 自动切 ≤12 字短行不跨句号）
   - **录最终 MP4**：`bash scripts/render-narration.sh demo.html --timeline=_narration/timeline.json [--bgm-mood=educational]` → 自动录无声 MP4 + 混入人声 + 可选 BGM
   - **失败模式 #1（必须避免）**：每个 Scene 各自独立 layout + cue 用 fade-up + scene 切换整页 opacity 切换 = **带配音的 PowerPoint** = 质感归零。完整规则见 `voiceover-pipeline.md` 头部「铁律」章节。

# UE 反射 / 蓝图 VM / AngelScript / 热更新 — 源码学习大纲（待 review 草案 v2）

> **状态：⚠️ 本文档仅是待用户 review 的学习大纲草案（v2），不是定稿，不含任何章节正文。**
> 所有章节只列「学习目标 / 核心问题 / 源码入口或案例入口 / 对照案例 / 最小实验 / 产出物与验收标准 / 预计课次」，不展开答案。
> 用户 review 通过后才会逐章产出正文；落盘后的仓库动作（p4 add、SKILL.md 索引、索引重建）也待批准后执行，见文末「大纲批准后的后续动作」。
>
> **v2 修订说明（响应 review 反馈）**：
> 1. **AngelScript 从「少量机制章」扩展为贯穿全课程的主线**：新增五级学习阶梯（L1 日常使用 → L2 应用模式 → L3 行为到原理映射 → L4 源码追踪 → L5 扩展与修改），AS 直接相关章节从 v1 的 4/23 章提升到 v2 的约 22/40 章，整体周期相应延长（不为控制章数压缩 AS）。
> 2. **先浅后深**：在全部底层/机制章节之前新增 10 个细粒度应用章（C1–C10，Phase A/B），全部绑定 `Main/Script/`、项目插件 Script 或现有 SKILL/reference 中**真实可定位**的项目案例（本次修订已逐一做有限定向检索核实，见第 7 节矩阵新增行）。
> 3. **深层部分形成渐进修改阶梯**：新增 Phase G（C31–C37），从「新增一个 AS 使用案例」逐级到「修改编译阶段/ThirdParty VM」「设计 reload/reinstancing 回归测试」，每级注明最小安全修改边界与验证方式（不写答案）。
> 4. 原 v1 的 C0–C22 内容与源码锚点**全部保留**，仅重编号（对照表见 §2 开头）；为避免与五级阶梯的 L1–L5 混淆，原「四层归属模型」的层级标签由 L1–L4 更名为 **T1–T4**（仅改名，内容不变）。
> 5. 网络/协程/异步：项目真实证据不足（详见 C10 与已知未知项 8/15），列为**可选/未知**章，不强行展开。
>
> **读者画像**：已有一点 C++ 反射基础（UCLASS/UPROPERTY/UHT 概念），AngelScript 与热重载零基础。学习策略：**先浅（会使用）后深（能修改）；小步学习、长期吃透**。
> **材料来源**：本大纲由两份只读勘察材料汇总而成（见文末附录 A），v2 新增案例锚点在落盘前做了有限定向复核（见「源码追踪矩阵」验证状态列）。
> **路径约定**：文中所有路径均为项目根相对路径（`D:\MainDev\` 省略）。行号基于当前 P4 工作区快照，**一律以符号名为主锚点、行号为辅**；同步 depot 后行号可能漂移，符号名稳定。

---

## 1. 全局心智模型

### 1.1 三套生产链，一个反射底座

本课程的全部内容挂在一张图上：**C++、Blueprint、AngelScript 三套"生产链"最终都汇聚到同一个 UObject 反射底座（UClass / UFunction / FProperty / CDO）**，运行时通过各自的执行体消费这个底座，编辑器期通过四套热更新系统就地替换它。

```
链 A (C++)    : .h/.cpp --UHT--> .gen.cpp --启动注册--> UClass/UFunction(native thunk) --Live Coding/HotReload 热更新
链 B (BP)     : EdGraph --Kismet 编译--> UFunction::Script 字节码 --VM(ProcessInternal)--> 执行 --BP Reinstancing 热更新
链 C (AS)     : .as --预处理/四阶段编译--> UASClass/UASFunction --context 池/JIT--> 执行 --AS Reload 热更新
                        汇聚层: UStruct/UClass/UFunction/FProperty/CDO（反射底座）
                        消费方示例: PLPythonPipeline 用同一套 FProperty API 无差别读写三条链产物的属性
```

「五层实体」指一条 AS 调用从静到动的五个形态：**`.as` 文本 → AS 模块（asCModule）→ UASClass/UASFunction（UClass 世界）→ CDO/实例 → 执行（context/JIT）**。每次热重载就是在不重启进程的前提下重建其中若干层。

### 1.2 四层归属模型（全课程的"图例"，v2 起标签更名 T1–T4）

读到任何一行代码、任何一个符号，先问它属于哪一层。四层归属是排障决策树的第一刀。（v2 注：为避免与 §1.4 的学习阶梯 L1–L5 混淆，归属层标签由 L1–L4 更名为 T1–T4，内容不变。）

| 层 | 范围 | 识别标记 | 代表证据 |
|---|---|---|---|
| T1 Epic UE 通用 | 引擎 stock 代码（本分支 UE 5.8.2） | 无标记 | `Engine/Source/Runtime/CoreUObject/Private/UObject/ScriptCore.cpp` `UObject::ProcessEvent`(:2083) / `ProcessInternal`(:1392)；`Class.cpp` `UFunction::Invoke`(:7595)；`Stack.h` `FFrame` |
| T2 Hazelight 引擎补丁 | 随 fork 带入的引擎修改，AS 运行的根基 | 注释标记 `// AS FIX(LV)` / `// HAZE FIX` | `Script.h:142` `FUNC_RuntimeGenerated`（占用 stock 未用位）；`Class.h` `RuntimeCallFunction`/`RuntimeCallEvent`/`GetRuntimeValidateFunction` 虚函数与 `bIsScriptClass`/`ScriptTypePtr`/`ASReflectedFunctionPointers` 字段；`CoreNative.h` ASAutoCaller 类型擦除；UHT C# 侧 `.ASFunctionPointers` 发射 |
| T3 AngelScript 插件 | `Engine/Plugins/Angelscript/`（三模块 AngelscriptCode/AngelscriptEditor/AngelscriptLoader，均 PostDefault；`ThirdParty/` 为 vendor fork VM 2.38.0-UE） | 插件目录本身 | `AngelscriptManager.cpp` `CompileModules`(:1798)；`ClassGenerator/AngelscriptClassGenerator.cpp`；`ThirdParty/SKILL.md` 记录的 fork 改造 |
| T4 项目层 | 项目自有代码与对引擎/插件的补丁 | `@CYANCOOK` 注释块（规范见 `docs/rules/cyancook-annotation.md`）；`Main/` 目录 | `Main/Script/`（全部 .as）；`Main/Plugins/PLPythonPipeline/`（本课程的反射实战教材）；GASExtendedPL ScriptTags；PLAutomation；引擎内 @CYANCOOK 点（如 `DuplicateDataReader.cpp`、`BlueprintCompilationManager.cpp:3455` 循环引用修复） |

⚠️ 勘察结论（待正文化时复核）：VM 核心文件（`Class.cpp`/`ScriptCore.cpp`/`KismetCompiler.cpp`/`KismetReinstanceUtilities.cpp`）在本分支**无 @CYANCOOK**——Blueprint VM 本体是 stock Epic，改动集中在 T2 标记块。grep 抓手：`grep -rn "AS FIX\|HAZE FIX"`（注意过滤 `Intermediate/*.i` 误中）。

### 1.3 贯穿教材：为什么选 PLPythonPipeline

`Main/Plugins/PLPythonPipeline/` 里的 `UPLPythonAutomationFunctionLibrary`（约 6.6k 行实现 + 全 UFUNCTION 声明头）是本项目**密度最高的真实反射实战代码**：FProperty 查找/类型判定/值读写/三种容器 Helper/DataTable 行内存/CDO/SCS/BPGC/资产生成/dry-run/JSON 互转全部有生产级用例，且每个 UFUNCTION 同时经 AS（`PLPythonAutomation::Func(...)`）与 Python（`unreal.PLPythonAutomationFunctionLibrary.func(...)`）静态绑定暴露——天然覆盖「反射 + 绑定 + 负结论（不使用 ProcessEvent）」三个主题。因此本课程让它**贯穿始终**：应用篇（C4/C8）用它做入门调用对象，机制篇（Phase C）每章用它做对照案例，Phase E 整篇是它的系统精读，L5 阶梯（C32）以「给它新增一个 UFUNCTION」为练手任务。

辅助读物（已有文档，勿重复造轮子）：本 skill 的 `SKILL.md`、`references/property-access.md`、`references/container-helpers.md`；`Main/Plugins/PLPythonPipeline/references/`（asset-query-extension / component-template-inheritance / bp-component-surgery / uasset-dissector）；`Engine/Plugins/Angelscript/SKILL.md` 及其 references；`Main/Script/SKILL.md`、`Main/Script/Editor/SKILL.md` 及各自 references（authoring-rules / troubleshooting / bp-migration 等）；`Main/Script/Editor/DataTableRowProcessor/SKILL.md`。

### 1.4 AS 五级学习阶梯（v2 新增，全课程主线）

AngelScript 不再是「一个 Phase」，而是贯穿全课程的主线。五个阶梯**顺序刚性**：每级的退出标准不齐，不进下一级。进入/退出标准同时是 review 与自验的勾选清单（沉淀为表 K）。

| 阶梯 | 名称 | 一句话目标 | 对应章节 | 进入标准 | 退出标准（不齐不进下一级） |
|---|---|---|---|---|---|
| **L1** | 日常使用 | 会写 .as、会跑、会看日志、会日常热更 | C0–C5（Phase 0 + A） | C0 完成；本机编辑器可启动；读过 `Main/Script/SKILL.md` | ① 能独立新增一个 AS 组件类并 hot reload 生效；② 能从 `ProjectLungfish.log` 的 LogAngelscript 频道定位并修好自己的编译错误；③ 能说清 soft/full reload 的现象差异与「新 C++ UFUNCTION 需重启」这一现象 |
| **L2** | 应用模式 | 会组织项目已有的六类模式：BP↔AS 协作、容器/委托/定时器/Tag/软引用、DT 自动化、调试测试 | C6–C10（Phase B） | L1 退出达成 | 不查资料能为「新技能 GA / 新编辑器菜单按钮 / 新 DataTable 批处理 / 新 PLAutomation 用例」选对模式并落地一个可运行实例 |
| **L3** | 行为到原理映射 | 把 L1/L2 的日常现象逐一映射到机制名词与文件符号 | C11–C14（Phase C） | L2 退出达成 | 对 ≥10 个日常现象（reload 三级判定、绑定找不到、PIE 降级、`default{}` 加载报错、缓存过期…）能说出对应机制名 + 文件 + 符号，且能用 C38 的观测抓手现场指认 |
| **L4** | 源码追踪 | 读得懂引擎/插件实现，能从现象追到代码行 | C15–C30（Phase D/E/F） | L3 退出达成 | 给定任一 AS 相关符号，能画出从 `.as` 文本到 VM/生成器/热更新的完整调用链；完成表 C/D/E 回填 |
| **L5** | 扩展与修改 | 能安全地修改绑定、类生成器、RuntimeCall 桥、编译阶段/VM，并为修改设计回归 | C31–C37（Phase G） | L4 退出达成 | 七级修改阶梯每级的「验证方式」全部真实执行通过；产出表 L（修改边界 → 验证矩阵） |

设计意图：**L1/L2 只要求「会用、会认现象」，机制解释一律标注「机制见 L3/L4」；L3 起才进入源码**。这保证学习曲线先平后陡，且每个深层概念都有读者亲手踩过的现象作锚。

---

## 2. 章节树（依赖序，Phase 0 → H）

每章固定 7 个字段：**学习目标 / 核心问题 / 源码入口或案例入口 / 对照案例（应用章为「真实项目案例（可定位）」）/ 最小实验 / 产出物与验收标准 / 预计课次**（1 课次 ≈ 60–90 分钟）。L5 章（C31–C37）额外含「最小安全修改边界 / 验证方式」两个字段。

**v1 → v2 章节编号对照**（内容保留，仅重编号；跨章引用已同步更新）：

| v1 | v2 | v1 | v2 | v1 | v2 |
|---|---|---|---|---|---|
| C0 | C0 | C8 | C18 | C15 | C25 |
| C1 | C15 | C9 | C19 | C16 | C26 |
| C2 | C16 | C10 | C20 | C17 | C27 |
| C3 | C17 | C11 | C21 | C18 | C28 |
| C4 | C11 | C12 | C22 | C19 | C29 |
| C5 | C12 | C13 | C23 | C20 | C30 |
| C6 | C13 | C14 | C24 | C21 | C38 |
| C7 | C14 | — | — | C22 | C39 |

新增章：C1–C10（Phase A/B 应用篇）、C31–C37（Phase G 修改阶梯）。

---

### Phase 0 — 全局地图

#### C0 三套生产链、五层实体、AS 五级阶梯与四套热更新地图

- **学习目标**：建立 §1 的全景心智模型；给出任意符号能判定四层归属（T1–T4）；知道 AS 五级阶梯（L1–L5）各自的进出标准；知道四套热更新（Live Coding / 旧 HotReload / BP Reinstancing / AS Reload）各自的管辖域。
- **核心问题**：① 一个调用从 `.as` 文本 / EdGraph / `.cpp` 到「被执行」各经过哪几层？三套链在哪一层汇合？② 四套热更新各自替换什么、保留什么？③ 为什么说 BP VM 本体在本分支是 stock Epic？④ 我当前处于阶梯哪一级、退出标准是什么？
- **源码入口**：`Engine/Source/Editor/LevelEditor/Private/LevelEditorActions.cpp` `RecompileGameCode_Clicked`（编译按钮分流 Live Coding vs HotReload）；grep 抓手 `AS FIX` / `HAZE FIX` / `@CYANCOOK`；`Engine/Plugins/Angelscript/SKILL.md` 与 `ThirdParty/SKILL.md`。
- **PLPythonPipeline·AS 对照案例**：跟踪一次 `PLPythonAutomation::GetObjectProperty(...)` AS 调用，指出它经过的每一层（T4 脚本 → T3 绑定 → T4 C++ 库 → T1 反射 API）。
- **最小实验**：用 grep 复现 T2/T4 marker 分布统计，亲手验证「VM 核心无 @CYANCOOK」这一勘察结论。
- **产出物与验收标准**：手绘四层归属图一张 + 三套生产链汇合图一张；能口述 `Main/Script/` 下任一 AS 类从文本到运行经过哪四层；能指出随机抽出的 5 个符号各属哪层；在表 K 上标记自己的起点。
- **预计课次**：1

---

### Phase A — AS L1 日常使用（会用）

> 本篇全部章节的机制解释一律只给「现象级陈述」，并标注「机制见 Phase C（L3）」。所有案例均已在 v2 修订时定向核实存在（见第 7 节矩阵）。

#### C1 AS 脚本目录与模块发现

- **学习目标**：知道 `.as` 该放哪、谁扫描、何时编译、为什么 Main/Script 里零 import 也能互相引用。
- **核心问题**：① `Main/Script/` 下新建子目录要不要注册？② 为什么名为 `Dev`/`Editor` 的目录在初始扫描中被跳过（现象层面）？③ 项目插件自己的 `Script/` 目录如何进入编译集合？④ 没有 import 语句，类型可见性从哪来？
- **源码入口**：`Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/AngelscriptManager.cpp` `MakeAllScriptRoots`(:268)/`FindScriptFiles` 跳过 `Dev`/`Editor`(:829/:837)；`Engine/Plugins/Angelscript/SKILL.md` code-locations 节（全局类型表 `allRegisteredTypesByName`/`allScriptDeclaredTypes` 的记述）；`Main/Script/SKILL.md` 目录结构节。
- **真实项目案例（可定位）**：`Main/Script/` 实际目录树（Gameplay/Component/Widget/Tests/Map/… 约 20 个一级目录）；`Main/Script/Map/<MapName>/Cells/` 这类后加子目录无需注册即可编译（`Main/Script/SKILL.md` code-locations 记载）；`Main/Script/Editor/` 全目录被 `#if EDITOR` 包裹的惯例（`Main/Script/Editor/SKILL.md` 常见模式节）。
- **最小实验**：在 `Main/Script/Utilities/` 新建一个最小 `.as` 类，保存后观察 LogAngelscript 热更日志确认被编译；再把它移入一个名为 `Dev` 的目录，验证不再被初始扫描收入（注意热更轮询与初始扫描的差异，机制留到 C11/C29）。
- **产出物与验收标准**：画出「脚本根 → 模块 → 类」归属图；能回答核心问题①–④（④允许只答到「全局类型表」现象层）。
- **预计课次**：1

#### C2 第一个 AS 类：类 / 属性 / 函数 / default 块 / 构造与生命周期

- **学习目标**：会声明 AS 类、UPROPERTY（含 `Transient`/`EditAnywhere`/`Category`）、UFUNCTION；理解 `default {}` 块的语义与限制的现象面；掌握生命周期入口的覆写规则。
- **核心问题**：① `default {}` 里能写什么、不能写什么（资产同步加载禁令的现象级陈述；机制根因见 C30）？② 为什么 `APLActorGAS` 子类要用 `K2_OnBeginPlay`/`K2_OnEndPlay`，而 `UActorComponent` 子类可直接覆写 BeginPlay/EndPlay？③ UPROPERTY 的 `Transient`/`EditAnywhere` 在 AS 里怎么写、对 BP 默认值面板意味着什么？④ AS 类有没有构造函数，和 `default {}` 是什么关系？
- **源码入口**：`Main/Script/references/angelscript-authoring-rules.md`（组件声明、覆写规则全文）；`Engine/Plugins/Angelscript/SKILL.md` core-rules 节（`default {}` 禁令原文）；`InitDefaultObjects` 作为 CDO 构建入口的名字先混个眼熟（机制见 C12/C30）。
- **真实项目案例（可定位）**：`Main/Script/Component/ASInteractionComponent.as`——UPROPERTY 用法谱系活样本（`TSoftClassPtr<UGameplayEffect>`、`Transient` 运行时态、`EditAnywhere + Category = "Interaction|Tip"` 分类、结构体容器 `TArray<FPLInteractionRule>`）；`Main/Script/Core/Visualization/DummyVisualizationComponent.as`——最小组件样本。
- **最小实验**：仿 `ASInteractionComponent` 写一个带 3 种 UPROPERTY（值类型 / 软引用 / Transient）的组件类，挂到测试 Actor 上，确认 BP 默认值面板可编辑、PIE 中 default 值生效。
- **产出物与验收标准**：产出一个可挂载、可在 BP 里编辑默认值的 AS 组件；能口述 `default {}` 禁令与 `K2_` 覆写规则；在 L1 退出清单上勾掉第一项的一半。
- **预计课次**：1–2

#### C3 常用宿主模式：Actor / Component / UObject / Subsystem

- **学习目标**：四类宿主的典型写法与适用场景；AS 侧实例化与获取方式。
- **核心问题**：① 什么时候该写 Component 而不是 Actor？② UObject 派生类在 AS 里如何实例化（哪些能裸构造、哪些必须走工厂/builder）？③ Subsystem 在 AS 里怎么拿到？④ AS 里给一个 Actor 动态加组件的惯用写法？
- **源码入口**：`Main/Script/SKILL.md` Authoring Rules 节（`SpawnActor(Class, ...)` 自由函数、`Owner.CreateComponent(...)`）；`Main/Script/Editor/SKILL.md` 关键类型节。
- **真实项目案例（可定位）**：Actor：`Main/Script/Actor/ASActorBed.as`（Actor + 定时器组合）；Component：`Main/Script/Component/ASInteractionComponent.as`；Subsystem 与委托：`Main/Script/Widget/Core/SubsystemWidget.as`；「AS 不能裸构造某些 C++ 类」的真实记录与 builder 对策：`Main/Script/Tests/1000_RuntimeTests/PLAutomationSampleCase.as` 头注释（`UPLLogAction` 不可构造 → 走 builder 的 `AddXxx` UFUNCTION）。
- **最小实验**：四类宿主各写一个最小实例并跑通（Subsystem 一章允许只在 PIE 里打印获取成功）。
- **产出物与验收标准**：产出四张「宿主 → 适用场景 → 实例化方式」卡片（沉淀为表 M 素材）；能回答核心问题①–④。
- **预计课次**：1

#### C4 调用 C++：UFUNCTION 调用与反射属性访问

- **学习目标**：会从 AS 调 C++ UFUNCTION（静态库函数 / 成员函数）；会读写反射属性；掌握命名规则的现象面。
- **核心问题**：① 函数库的 AS 命名空间为什么不等于类名（`UPLBuildingFunctionLibrary` → `PLBuilding::`）？② 「C++ 函数脚本里找不到」第一排查顺序是什么（现象层：先查命名空间剥离与前缀规则，机制见 C13）？③ `WITH_EDITORONLY_DATA` 属性不在绑定里时，怎么按名读写？④ 调用一个不存在的函数与调用一个类型不匹配的函数，报错形态有何不同？
- **源码入口**：`Main/Plugins/PLPythonPipeline/Source/PLPythonPipeline/Public/PLPythonAutomationFunctionLibrary.h`（UFUNCTION 声明样本库）；`Main/Script/SKILL.md` Top 陷阱节（命名空间剥离、`GetObjectProperty` 按名读兜底）。
- **真实项目案例（可定位）**：`Main/Script/Editor/DataTableRowProcessor/DataTableRowProcessor_PLEntityTagMapping.as` 对 `PLPythonAutomation::` 的真实调用现场（`GetObjectProperty` as:449、`SetEditorObjectProperty` as:476、`SetGameplayTagContainerProperty` as:477 等）；GAS 事件分发 `AbilitySystem::SendGameplayEventToActor(...)`（authoring rules 记载的正确写法）。
- **最小实验**：在编辑器脚本里分别调 3 个不同来源的 C++ UFUNCTION（PLPythonAutomation 静态库 / 某个 Component 成员 / 一个 GAS 自由函数），并故意写错一次命名空间观察报错文本。
- **产出物与验收标准**：产出「找不到函数 → 排查顺序」小抄一条（沉淀为表 F 素材）；能回答核心问题①–④。
- **预计课次**：1

#### C5 日常迭代工作流：soft/full reload、日志与排错入门

- **学习目标**：跑通「改 .as → 自动热更 → 看日志 → 修错」的日常闭环；建立 soft/full reload 的现象级认识。
- **核心问题**：① 什么改动会触发 full reload（现象层：加 UPROPERTY / 改布局）？② 日志里 `Hot reload failed due to script compile errors. Keeping all old script code.` 意味着什么、之后编辑器处于什么状态？③ PIE 中改脚本会发生什么（现象层）？④ 无编辑器环境下怎么验证本目录脚本编译（headless commandlet）？
- **源码入口**：`Main/Script/SKILL.md` Debugging 节（日志频道、`AS.ReloadAll`/`AS.ListScripts`/`AS.DumpBindings`）；`Main/Script/Editor/SKILL.md` Troubleshooting 节（headless 验证命令：`-run=AngelscriptAllScriptRoots -as-force-preprocess-editor-code -as-ignore-precompiled-data -unattended -nullrhi`）。
- **真实项目案例（可定位）**：`Main/Saved/Logs/ProjectLungfish.log` 的 LogAngelscript 频道真实输出；`Main/Script/Editor/` 目录全部 `.as` 即 headless 命令的验证对象。
- **最小实验**：完整走一遍三连：改函数体 → 观察 soft reload；加 UPROPERTY → 观察 full reload；制造一个编译错误 → 读日志定位 → 修复恢复。
- **产出物与验收标准**：勾掉 L1 退出标准②③；产出个人「热更日志关键词」便签（保存失败/成功/回退三种文本）。
- **预计课次**：1

---

### Phase B — AS L2 应用模式（会组织）

> 进入本篇即进入 L2。每章对应项目里一类反复出现的组织模式，案例全部可在仓库内定位。

#### C6 BlueprintEvent / BlueprintOverride 与 BP↔AS 协作模式

- **学习目标**：掌握项目标准协作模式「C++ 基类暴露事件 + AS 子类 `UFUNCTION(BlueprintOverride)` 覆写」；理解覆写命名规则与遮蔽陷阱。
- **核心问题**：① 为什么只有事件型接口（BlueprintNativeEvent/BlueprintImplementableEvent）才能被 AS 子类覆写（规则层；机制见 C13）？② AS 覆写为什么不带 `_Implementation` 后缀？③ BP 父类事件图里有 `ReceiveBeginPlay` 时，AS 的 `BlueprintOverride BeginPlay` 为什么静默不执行、对策是什么（惰性 Ensure 模式）？④ `BlueprintOverride, BlueprintCallable` 组合何时需要？
- **源码入口**：预处理覆写映射 `AngelscriptPreprocessor.cpp:1426–1452`、类生成强制校验 `AngelscriptClassGenerator.cpp:444–507`（**二手引用，来自团队计划文档 `.team/sunlaibing/plans/runtime-details-as-script-execution-plan.md`，正文化前须复核**——本章只要求知道存在这两个把关点）。
- **真实项目案例（可定位）**：`UPLDamageFlowCalculation` → `Main/Script/Gameplay/Entry/ASDamageFlow_*.as`（17 个真实 AS 子类，C++ 侧 `NewObject` 实例化，见 `Main/Script/SKILL.md` code-locations）；`UPLAutomationAction` → `Main/Script/Tests/1000_RuntimeTests/PLAutomationSampleCase.as` 的 `UWaitTicksAsAction`（纯 AS 编写的新 Action，`BlueprintOverride Tick`）；UMG 侧大量 `BlueprintOverride` 样本（如 `Main/Script/Widget/Wheel/Wheel_Building.as`、`Main/Script/Widget/Table/WindMill/WindMillWindow.as:24` 的组合写法）。
- **最小实验**：挑一个 `ASDamageFlow_*` 子类，对照其 C++ 基类声明，逐个指出哪个 UFUNCTION 是覆写点；再故意把覆写函数名写错一次，看强制校验的报错形态。
- **产出物与验收标准**：能回答核心问题①–④；产出「覆写三规则」卡片（事件型 / 不带 _Implementation / 防遮蔽）。
- **预计课次**：1–2

#### C7 容器 / 委托 / 定时器 / GameplayTag / 资产与软引用

- **学习目标**：掌握 AS 里五类高频语言设施的项目惯用法：TArray/TMap、事件委托绑定、定时器、GameplayTag（`GameplayTags::` 语法糖与 `ScriptTags::Define`）、软引用（TSoftObjectPtr/TSoftClassPtr）。
- **核心问题**：① AS 里容器声明与遍历的项目惯用写法？② 委托绑定的惯用形式（`AddUObject` 系）？③ 定时器怎么设、怎么清？④ `GameplayTags::X_Y` 语法糖从哪来、为什么 `namespace GameplayTags` 里不能自定义路径下划线变量名？⑤ 软引用字段什么时候 `.LoadSynchronous` 是合法的、什么时候必须挪到运行期（呼应 C2 的 `default {}` 禁令）？
- **源码入口**：`Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/Binds/Bind_FGameplayTag.cpp:40–59`（tag 自动绑定为 `GameplayTags::` 全局量的实现位置，名字混眼熟即可）；`Main/Script/SKILL.md` Script-Defined GameplayTags 节（单行字面量铁律、add-only 约束）。
- **真实项目案例（可定位）**：容器+软引用：`Main/Script/Component/ASInteractionComponent.as`；定时器：`Main/Script/Actor/ASActorBed.as` 等 Actor 组（`System::SetTimer/ClearTimer` 真实使用）；委托：`Main/Script/Widget/Core/SubsystemWidget.as`、`Main/Script/Character/ASCharacterPlayer.as`；GameplayTag 语法糖使用：`Main/Script/Gameplay/Ability/ASAbility_AimingBase.as` 等 Ability 组；tag 定义：`Main/Script/Tags/**/*.as`；自动绑定命名冲突的真实事故（5674 条 `Name conflict`）：`Main/Script/Editor/SKILL.md` Troubleshooting 第一节。
- **最小实验**：给一个组件同时加上：一个 `TArray` 属性、一个 `TSoftClassPtr` 属性、一个定时器轮询、一次委托绑定、一次 `GameplayTags::` 读取，PIE 里全部验证。
- **产出物与验收标准**：五设施各产出一张惯用法卡片（沉淀为表 M 素材）；能复述 tag 冲突事故的成因与规避（`namespace GameplayTagDefs`）。
- **预计课次**：2

#### C8 DataTable 与 PLPythonPipeline 编辑器自动化

- **学习目标**：掌握「Excel → Python exporter → AS 行处理器 → C++ 反射写回」这条项目独有的数据管线在 AS 侧的写法；掌握编辑器批处理三纪律（测试限流 / 表新鲜度 / 事务与保存）。
- **核心问题**：① DataTable 行在 AS 里怎么读（FindRow/GetAllRows 的行结构精确匹配约束）？② `DataTableRowProcessor_*` 框架的职责划分（AS 侧做什么、C++ 侧做什么）？③ 批处理为什么要 `bTestMode` 限流、跑写操作前为什么要 `CheckAssetExistsAndIsUpToDate`？④ `Editor::BeginTransaction/EndTransaction` 与 `MarkPackageDirty`/`SaveLoadedAsset` 各自管什么？
- **源码入口**：`Main/Script/Editor/SKILL.md`（菜单扩展、批处理套路、测试限流、表新鲜度四节）；`Main/Script/Editor/DataTableRowProcessor/SKILL.md`；`Main/Plugins/PLPythonPipeline/SKILL.md`。
- **真实项目案例（可定位）**：`Main/Script/Editor/DataTableRowProcessor/DataTableRowProcessor_PLEntityTagMapping.as`（全链路主案例）；`Main/Script/Editor/DataAutomationUtility.as`（`RefreshPLPhaseComponentToDataAsset`：BP 组件 tag → DataAsset 同步）；`Main/Script/Editor/UseCases/`（`UPLDataTableTestingUseCase` 读表 API 活样例、`UBaseUseCase` 弹窗/日志基类）；`Main/Script/Editor/EditorMenuExtensions.as`（`Excel2DA_*` 按钮 → `Content/Python/excel_exporter.py`）；限流/新鲜度范本：`EditorMenuExtensions_Temp.as` 的 `Temp_CleanAttributeSet`、`DT_EntityPropertyInitializer` 按钮。
- **最小实验**：照 `Temp_CleanAttributeSet` 结构写一个限流批处理（只处理前 N 行），先 dry-run 读日志再真跑；用 `UPLDataTableTestingUseCase` 的读表 API 打印一张表的行数与属性名。
- **产出物与验收标准**：产出「编辑器批处理 checklist」一条（限流/新鲜度/事务/保存/dry-run）；能回答核心问题①–④。
- **预计课次**：1–2

#### C9 调试 / 日志 / 自动化测试

- **学习目标**：配齐 AS 的调试手段：VSCode 断点、日志频道、PLAutomation AS 用例的编写与运行。
- **核心问题**：① VSCode 怎么连上编辑器里的 AS DebugServer、reload 后断点为何需要 Reapply？② PLAutomation 用例的骨架长什么样（`UPLAutomationCaseBase` + `BuildSequence` + 链式 `.Add`）？③ `ue-cli run-plauto` 的 filter 规则（`PLAutomation.` 前缀）与 run-tests 的分工？④ 为什么 unattended 下「脚本编译失败但退出码为 0」，自动化判读该看什么？
- **源码入口**：`Main/Script/Tests/SKILL.md`（测试层分层与 SequenceBuilder）；`.claude/skills/ue-cli-automation/SKILL.md`；`Main/Script/SKILL.md` Debugging 节；命令行 `-asdebugport=`（`Engine/Plugins/Angelscript/SKILL.md` troubleshooting 引用）。
- **真实项目案例（可定位）**：`Main/Script/Tests/1000_RuntimeTests/PLAutomationSampleCase.as`（纯 AS Action + 链式序列的完整可运行样本）；`Main/Script/Tests/` 分层目录（0100_FunctionTest / 1000_RuntimeTests / 2000_IntegrationTest / 3000_QATests / 9000_Developers）真实存在；委托断言样本 `Tests/1000_RuntimeTests/HUDFade/TestCase_7806_*.as`。
- **最小实验**：仿 `PLAutomationSampleCase` 写一个新用例（一次日志 + 一次属性断言），用 `ue-cli run-plauto --filter` 跑通；VSCode 连调试器命中一个 AS 断点。
- **产出物与验收标准**：勾掉 L2 退出标准中「新 PLAutomation 用例」一项；产出「测试 filter 与退出码判读」便签。
- **预计课次**：1–2

#### C10（可选 / 证据待定）网络复制、协程与异步

- **学习目标**：（本章当前为**可选/未知**占位章，仅在证据补齐后正文化。）了解 AS 侧网络复制与协程/异步的项目现状与边界。
- **核心问题**（当前只列问题，不给答案）：① AS 里哪些 UPROPERTY 可复制、RPC 怎么写？② HAZE 的 `WITH_ANGELSCRIPT_HAZE` 网络层（CrumbFunction）在本分支是否启用？③ 协程/await 在项目里的真实形态是什么？
- **源码入口（现状证据）**：`Main/Script/Tests/1000_RuntimeTests/Net/` 目录真实存在（v2 已核实），可作网络用例导读起点；`Engine/Plugins/Angelscript/ThirdParty/SKILL.md` 对 VM Suspend 的记述；PLScriptAsync 插件——⚠️ **head 只有 SKILL.md，实现位于未提交 shelf 119677/117988**（已知未知项 2/8/15），机制正文待 rebase 后补。
- **真实项目案例（可定位）**：`Tests/1000_RuntimeTests/Net/` 内用例（作为「项目确实有网络相关 AS 测试」的最小证据）；其余标注未知。
- **最小实验**：通读 `Net/` 目录用例清单并归类（复制 / RPC / 同步语义各占多少）；不写机制结论。
- **产出物与验收标准**：产出「C10 证据缺口清单」——哪些问题的答案当前只能标未知；本章不计入 L2 退出标准。
- **预计课次**：0–1

---

### Phase C — AS L3 行为到原理映射（机制层）

> 本篇 = v1 Phase 2 四章，定位从「机制学习」改为「把 Phase A/B 踩过的现象映射到机制」。每章开头建议先回顾对应的现象清单。C15（Epic 反射底座）是 C12/C13 的软依赖，可与本篇并行插读。

#### C11 AS 编译管线与模块加载（v1 C4）

- **学习目标**：Loader 引导 → Manager.Initialize（TaskGraph worker 线程）→ 脚本根扫描 → Preprocessor（UCLASS 宏/#if flag）→ CompileModules 分阶段编译，全链路走一遍；把 C1/C5 的现象（目录跳过、热更日志、编译错误诊断）逐一落到机制。
- **核心问题**：① 四阶段（parse/类型生成/布局/编译）各自的产物与失败表现？② 为什么本 fork 的 `asCModule::Build()` 是空壳、手动编译必须复刻 Manager 的分阶段序列？③ `FindScriptFiles` 为何跳过 `Dev`/`Editor` 目录（C1 现象的机制答案）？
- **源码入口**：`Engine/Plugins/Angelscript/Source/AngelscriptLoader/`（引导）；`AngelscriptCode/Private/AngelscriptManager.cpp` `MakeAllScriptRoots`(:268)/`InitialCompile`(:892)/`CompileModules`(:1798)、跳过目录(:829/:837)；分阶段序列：:1827 defer 标志 → :1928 `BuildParallelParseScripts` → :1949 `BuildGenerateTypes` → :3032 `BuildGenerateFunctions` → :2409 `BuildLayoutClasses` → :2415 还原 defer → :2469 `BuildLayoutFunctions` → :3049 `BuildCompileCode` → :2559 `BuildCompleted` → :3066 `ResetGlobalVars`；`ThirdParty/source/as_module.cpp` `asCModule::Build()` 空壳（约 :290）。
- **PLPythonPipeline·AS 对照案例**：`Main/Script/Editor/DataTableRowProcessor/DataTableRowProcessor_PLEntityTagMapping.as`——一个真实被这条管线编译、且在 dry-run 中全链路执行的项目脚本（调用 `PLPythonAutomation::CreateAssetsFromDataTable` 等，as:174/297/449/476/477 区域）。
- **最小实验**：新增一个 `.as`，读 `Main/Saved/Logs/ProjectLungfish.log` Angelscript 频道的阶段耗时；故意制造编译错误观察诊断格式（与 C5 实验对照，这次要说出发生在哪个阶段）。
- **产出物与验收标准**：复述四阶段产物与各自失败表现；能解释「为什么不能自己 new module 调 `Build()`」；把 C1/C5 的每条现象标注到具体阶段。
- **预计课次**：2

#### C12 类型与函数注册（编译产物 → UClass）（v1 C5）

- **学习目标**：`.as` 类如何变成 `UASClass`/`UASFunction`；reload 需求分级；属性/函数 Desc → UFunction；约 40 个 RuntimeCallFunction 特化子类的作用；C2 的 `default {}`/CDO 现象的机制答案。
- **核心问题**：① `UASFunction` 相对普通 UFunction 多了什么（ScriptFunction/JitFunction/参数行为表），`Func` 最终指向谁？② `FUNC_RuntimeGenerated` 在哪置位、被谁消费？③ CDO 在 AS 类上如何构建（`InitDefaultObjects`）？
- **源码入口**：`Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/ClassGenerator/AngelscriptClassGenerator.cpp` `AddModule`(:62)/`ShouldFullReload`(:2091)/`PerformReload`(:2116)/`FUNC_RuntimeGenerated` 置位（约 :3322，待复核）/`InitDefaultObjects`(:5828)；`Public/ClassGenerator/ASClass.h`（约 :124–219）；`Engine/Source/Runtime/CoreUObject/Public/UObject/Class.h` `bIsScriptClass`/`ScriptTypePtr`（约 :4026 区域）；`Script.h:142`。
- **PLPythonPipeline·AS 对照案例**：在编辑器里反射查看 AS 侧 `PLPythonAutomation::*` 调用的目标 UFunction 形态（库函数是 native UFUNCTION，对照 AS 类自身函数的 RuntimeGenerated 形态）。
- **最小实验**：`AS.ListScripts` + 反射查看一个 AS 类的 FunctionFlags，找到 `FUNC_RuntimeGenerated`。
- **产出物与验收标准**：解释 UASFunction 的 Func 指向与参数行为表；画出 .as 类 → UASClass 的生成流程图；把 C2 的 `default {}` 禁令标注到 `InitDefaultObjects`。
- **预计课次**：2

#### C13 双向桥接（UE↔AS）（v1 C6）

- **学习目标**：UE→AS 的虚函数注入（T2 补丁）与 AS→UE 的静态绑定两条路径；参数在哪一层打包/解包；命名规则（C4/C6 现象的机制答案）。
- **核心问题**：① `ProcessEvent` → `RuntimeCallEvent` 的分派点在 ScriptCore.cpp 哪里、NetValidate 路径有何不同？② `AngelscriptCallFromBPVM` 模板如何解析脚本虚函数（vfTableIdx/JIT 快路径）？③ 自动绑定（126 个 `Bind_*.cpp`）与手写绑定（`AngelscriptBinds.h`/容器模板）的分工？④ 前缀剥离（K2_/BP_/AS_/Receive）与 @CYANCOOK 属性同名回退规则（C4 命名现象 + C6 覆写校验的机制答案）？
- **源码入口**：T2 侧 `ScriptCore.cpp` :1154/:1203–1217（CallFunction 分派 native vs RuntimeCallFunction）/:1356/:2114+/:2147–2215；插件侧 `ASClass.cpp` `AngelscriptCallFromBPVM`（约 :105，:101 ResolveScriptVirtual；:1918 起 40 个特化）；绑定侧 `Private/Binds/Bind_BlueprintCallable.cpp`、`Helper_FunctionSignature.h:100–107`（前缀剥离）+ @CYANCOOK :122–127（属性同名回退）、`Bind_BlueprintEvent.cpp`、`Public/AngelscriptBinds/Bind_TArray.h`；覆写把关点 `AngelscriptPreprocessor.cpp:1426–1452` / `AngelscriptClassGenerator.cpp:444–507`（二手引用，待复核）。
- **PLPythonPipeline·AS 对照案例**：`PLPythonAutomation::Func(...)`（AS）与 `unreal.PLPythonAutomationFunctionLibrary.func(...)`（Python）两条静态绑定路径——这是 PLPythonPipeline 全部 UFUNCTION 的暴露机制，也是 C16 负结论「无 ProcessEvent」的结构原因：**调用方是 AS/Python，绑定在编译期完成，运行期无需反射式函数调用**。
- **最小实验**：BP 调 AS 函数、AS 调 C++ UFUNCTION 各断点走一遍；给一个「脚本里找不到的 C++ 函数」定位是否命中命名回退（C4 实验的机制复跑）。
- **产出物与验收标准**：画出双向调用链，标出参数打包/解包层与虚函数覆写解析点；复述命名回退规则；把 C6 的「覆写三规则」逐条映射到预处理/类生成把关点。
- **预计课次**：2

#### C14 AS 运行时执行环境（v1 C7）

- **学习目标**：context 池、异常与调用栈、游戏线程纪律、StaticJIT 预编译、VSCode DebugServer、Binds.Cache（C9 调试体验的机制答案）。
- **核心问题**：① context 池（`AS_MAX_POOLED_CONTEXTS`）的复用语义？② `GIsInAngelscriptThreadSafeFunction` 守的是什么？③ Binds.Cache 与 PrecompiledScript.Cache 各自解决什么问题、何时过期？④ `-as-simulate-cooked` 能复现哪类 cooked/编辑器差异？
- **源码入口**：`AngelscriptManager.h:13`（池尺寸）；`AngelscriptManager.cpp` 行号 cues(:354/:380)、PrecompiledScript 加载(:363)、Binds.Cache 写出(:407/:427，写出侧实现未读——见已知未知项)；`Private/Testing/AngelscriptTest.cpp:385` `FAngelscriptContext` 执行原语；命令行 `-as-generate-precompiled-data`/`-as-ignore-precompiled-data`/`-as-simulate-cooked`/`-asdebugport=`。
- **PLPythonPipeline·AS 对照案例**：Excel dry-run 全链路真实执行 `RunEntityTagMappingRow`（`Content/Python/excel_exporter.py:370` 起）时 AS 运行时扮演的角色；PLAutomation AS 用例（`ue-cli run-plauto`，C9）的宿主环境。
- **最小实验**：VSCode 连调试器打断点（含 reload 后 ReapplyBreakpoints，与 C9 实验互证）；编辑器加 `-as-simulate-cooked` 复现一个 cooked 行为差异。
- **产出物与验收标准**：说清 Binds.Cache 与 PrecompiledScript.Cache 的分工与失效条件；能在 VSCode 里命中 AS 断点。本篇结束即完成 L3 退出验收（≥10 条现象→机制映射）。
- **预计课次**：1–2

---

### Phase D — Epic 通用底座（L4 地基，复习对齐 + 补齐 VM）

> v1 Phase 1 整体后移至此。定位：L4 源码追踪的地基篇；C15 是 Phase C 的软依赖，可提前插读。

#### C15 C++↔反射链（对齐 5.8 现状）（v1 C1）

- **学习目标**：把既有 UCLASS/UPROPERTY/UHT 概念对齐到本分支源码；理解注册产物（UClass/UFunction/FProperty）的内存形态；知道本 fork 的 UHT 额外为 AS 发射 `ASFunctionPointers`。
- **核心问题**：① `.gen.cpp` 里的注册代码在启动哪一刻执行、产物挂到哪？② `UFunction::Func` 指针从哪来、native thunk 长什么样？③ `ASFunctionPointers` 字段相对 stock UHT 多了什么、为谁服务？
- **源码入口**：`Engine/Plugins/Angelscript/Source/AngelscriptCode/Public/ClassGenerator/CoreNative.h`（ASAutoCaller 类型擦除方法指针，约 :25–227）；`Engine/Source/Runtime/CoreUObject/Private/UObject/Class.cpp` `AddNativeFunction` 旁路挂 `ASReflectedFunctionPointers`（约 :176 区域，待复核）；UHT C# 侧 `UhtHeaderCodeGeneratorCppFile.cs` `GetASFunctionPointers`（约 :2894–3029，发射点约 :3082–3085，待复核）。
- **PLPythonPipeline·AS 对照案例**：`UPLPythonAutomationFunctionLibrary`（`Main/Plugins/PLPythonPipeline/Source/PLPythonPipeline/Public/PLPythonAutomationFunctionLibrary.h`）作为一个普通 `UBlueprintFunctionLibrary` 的注册产物；`PLPYTHONPIPELINE_API` 与静态 UFUNCTION 的组织方式。
- **最小实验**：挑一个项目 C++ 类，读它的 `.gen.cpp`，找到 ASFunctionPointers 相关字段/注册段。
- **产出物与验收标准**：画出 UClass/UFunction/FProperty/Func 指针来源图；能回答核心问题①②③。
- **预计课次**：1–2

#### C16 Blueprint VM 运行时（v1 C2）

- **学习目标**：理解 FFrame（Code 游标/Step/Locals/OutParms）→ ProcessEvent → Invoke → `(*Func)` 三分派；ProcessInternal 的 opcode 循环与 `exec*` 处理器族。
- **核心问题**：① `UFunction::Bind` 在非 Native 时把 Func 绑给谁？② `ProcessEvent` → `Function->Invoke` → `ProcessInternal` 的调用序与各自职责？③ EX_* token 流如何对应回 BP 节点语义？
- **源码入口**：`Engine/Source/Runtime/CoreUObject/Public/UObject/Stack.h` `FFrame`；`ScriptCore.cpp` `UObject::ProcessEvent`(:2083)、`DEFINE_FUNCTION(UObject::ProcessInternal)`(:1392)、`ProcessLocalScriptFunction`(:1245)；`Class.cpp` `UFunction::Invoke`(:7595)；`UFunction::Bind`。
- **PLPythonPipeline·AS 对照案例（负结论预埋）**：`PLPythonAutomationFunctionLibrary.cpp` 全文无 `ProcessEvent`/`FindFunction` 动态函数调用——UFunction 仅以「数据」身份出现：`Utils/EditorExBPLibrary.cpp:298` `FindFieldChecked<UFunction>(UKismetSystemLibrary::StaticClass(), Name)` 造 K2 CallFunction 节点模板。带着「为什么不需要」进入 Phase C/C13。
- **最小实验**：断点跟一个 BP 函数调用，观察 `FFrame.Code` 走带与 EX_* token。
- **产出物与验收标准**：能读一小段 `UFunction::Script` 字节流并说出对应节点语义；画出一次 BP 调用的栈帧图。
- **预计课次**：2

#### C17 Kismet 编译管线（v1 C3）

- **学习目标**：理解 `FKismetCompilerContext` 各阶段（函数清单 → 类布局 → 函数编译）→ VM backend 写字节码；`FBlueprintCompilationManager` 的编排/队列/Flush。
- **核心问题**：① EdGraph → `UFunction::Script` 的路径经过哪些阶段产物？② 「增量编译队列」何时被 Flush、Flush 触发什么连锁？③ 类布局（`CompileClassLayout`）与函数编译为何分阶段？
- **源码入口**：`Engine/Source/Editor/KismetCompiler/Private/KismetCompiler.cpp` `CreateFunctionList`(:4685)/`CompileClassLayout`(:4749)/`CompileFunctions`（约 :4956）/`MergeUbergraphPagesIn`（约 :3813）；`KismetCompilerVMBackend.cpp` `FScriptBytecodeWriter`/`FContextEmitter`；`Engine/Source/Editor/Kismet/Private/BlueprintCompilationManager.cpp` `FlushCompilationQueueAndReinstance`(:4563)/`CompileSynchronously`(:4599)/`QueueForCompilation`。
- **PLPythonPipeline·AS 对照案例**：`PLPythonAutomationFunctionLibrary.cpp` `RefreshAndCompileBlueprint`（约 :6275）——程序化触发 BP 编译的最小封装；BP 图手术函数群（`BreakOrphanedPinLinks`/`AddObjectMemberVariable`/`BindVariableNode`/`DumpFunctionGraph`，约 :6286–6400）作为「编译前端产物被工具消费」的实例。
- **最小实验**：编译一个 BP，对照日志/断点确认各阶段产物（类布局 → 函数清单 → 字节码）。
- **产出物与验收标准**：讲清 EdGraph → `UFunction::Script` 的路径；说出 FlushCompilationQueueAndReinstance 的两个真实触发场景（其中一个在 C29 交汇点）。
- **预计课次**：2

---

### Phase E — PLPythonPipeline 真实反射用例（L4 系统精读）

> 硬依赖只有 C15+C16（Epic 反射底座）；与 Phase C 并行学习亦可。每章仍以「AS 调用侧」作对照，呼应 C13。

#### C18 FProperty 查找与类型判定（v1 C8）

- **学习目标**：三类宿主（UClass 含 BPGC / UScriptStruct / UUserDefinedStruct）统一抽象为 UStruct 被 `TFieldIterator<FProperty>` 同质遍历；Blueprint 命名噪音（GUID 后缀/`_GEN_VARIABLE`/`_C`）与三种匹配策略；类型判定层级。
- **核心问题**：① 为什么 BP 结构体字段不能精确名匹配？② `CastField` 返回 null 的两类原因？③ `SameType()` 与 `GetClass()==GetClass()` 的口径差（`PLWaterBodyMigrationLibrary.cpp:152` 为何选后者）？④ 名字再映射两种风格（正则剥离 `ProcessPropertyName` vs 静态映射表 `GetMappedPropertyName`/`GetCollisionConfigMappedPropertyName`）各自的适用面？
- **源码入口**：`Main/Plugins/PLPythonPipeline/Source/PLPythonPipeline/Private/PLPythonAutomationFunctionLibrary.cpp` `PLPythonAutomationHelpers::CopyPropertyValue`（:136–276 全函数）；`ExtractCollisionConfigFromAnimMontage` 的 BP 结构体字段前缀匹配（:5173–5181）；引擎 `CoreUObject/Public/UObject/UnrealType.h` FObjectPropertyBase/FObjectProperty 继承；对照本 skill `SKILL.md` 的 CastField 速查表。
- **PLPythonPipeline·AS 对照案例**：本章即主教材；AS 侧对照：`DataTableRowProcessor_PLEntityTagMapping.as:449` `PLPythonAutomation::GetObjectProperty` 的调用现场（C4 已亲手调过）。
- **最小实验**：对一个实体 BP CDO 调 `GetObjectProperty(n"ItemDefinition")` 读取，再故意传错属性名观察 LogW；对 BP 结构体字段分别试 `FindPropertyByName` 精确名（应失败）与 `StartsWith` 前缀（应成功），打印 `Prop->GetClass()->GetName()`。
- **产出物与验收标准**：能回答核心问题①–④；整理一张「命名噪音 → 匹配策略」对照小抄（沉淀为表 H 素材）。
- **预计课次**：1

#### C19 值读写三件套与「先比后写」（v1 C9）

- **学习目标**：`ContainerPtrToValuePtr` 取地址 → 类型化 `Get/SetPropertyValue[_InContainer]`；`Identical()` 比较 → `CopyCompleteValue()` 拷贝范式；bool 位域陷阱；写后通知。
- **核心问题**：① 为什么 bool 必须走 `Get/SetPropertyValue_InContainer` 而非 `Identical`+裸指针？② `ContainerPtrToValuePtr` 的实参是「对象指针」与「行内存指针」时语义有何不同？③ 写 UObject 属性后忘调 `PostEditChangeProperty` 会怎样？④ `ConvertAndSetPropertyValueEx` 三态（Changed/NoChange/Unsupported）的设计动机？
- **源码入口**：`PLPythonAutomationFunctionLibrary.cpp` `CopyPropertyValue` bool 特判段（:224–244 区域）与注释；`SetBoolProperty`(:4344) 与 `SetStringProperty`(:4146)/`SetIntProperty`(:4212)/`SetFloatProperty`(:4278) 四个同构守门模板对照；`ExportPropertyValueForDryRun`(:277)；`ConvertAndSetPropertyValue`(:3447)/`ConvertAndSetPropertyValueEx`(:3455)、不支持类型日志(:3619–3622)；引擎 `CoreUObject/Private/UObject/PropertyHelper.h`（注意在 Private）。
- **PLPythonPipeline·AS 对照案例**：`SetEntityPropertiesFromDataTableRow`(:3375) 走三态写实体 CDO 的完整入口；AS 侧 `SetEditorObjectProperty` 调用（as:476）。
- **最小实验**：对同一属性先写新值再写同值，观察第二次返回 NoChange/false；用 `ExportText_Direct` 打印一个 `TSoftClassPtr` 与一个 `FGameplayTagContainer` 的文本形态。
- **产出物与验收标准**：能回答核心问题①–④；产出「先比后写」范式卡片一张。
- **预计课次**：1

#### C20 容器属性运行时操作（v1 C10）

- **学习目标**：`FScriptMapHelper`/`FScriptArrayHelper`/`FScriptSetHelper` 三种 Helper 的遍历与写回；Inner/ElementProp/KeyProp/ValueProp 直接成员访问风格；map 内嵌 struct 字段的三层指针路径。
- **核心问题**：① `GetValueProperty()`/`GetKeyProperty()` 返回值为何要 `const` 接收？② `FScriptMapHelper` 为何有 `IsValidIndex` 空洞？③ 写回 map 内嵌 struct 字段的正确指针路径（Map→ValuePtr→内层 FProperty→ContainerPtrToValuePtr）？④ Helper 构造时传入的 ptr 指向什么？
- **源码入口**：本 skill `references/container-helpers.md` 全文；`ExtractCollisionConfigFromAnimMontage` 的 Map 段（:5130–5210，`FMapProperty`+`FScriptMapHelper` 遍历 `TagCollisionPackages`）；`ClearPhaseComponentAttributeInitializationData`(:4410，最小 Array 案例)；`Utils/EditorExBPLibrary.cpp` :83–175（Array 增删读写全流程）；`Utils/PLWaterBodyMigrationLibrary.cpp` :40–110（三种 Helper 同台）。
- **PLPythonPipeline·AS 对照案例**：`EntityNames` `TMap<FGameplayTag,FText>` 遍历回写实体 BP CDO（`SetEntityPropertiesFromDataTable` :635–806 内）；AS 侧经 `SetGameplayTagContainerProperty`（as:477）写入。
- **最小实验**：对一个带 `TMap<FGameplayTag, struct>` 的 notify 实例遍历并打印每个 key；向数组属性 `AddValue` 一个元素再 `EmptyValues`。
- **产出物与验收标准**：能回答核心问题①–④；能手画 map 内嵌 struct 的三层指针图。
- **预计课次**：1–2

#### C21 BPGC / SCS / CDO / 组件模板（v1 C11）

- **学习目标**：CDO 获取与「写 CDO = 改蓝图默认值」；UBlueprint→GeneratedClass→CDO 自动解引用前奏；父类优先 SCS 收集与覆写模板（ICH）；`_C`/`_GEN_VARIABLE` 后缀边界。
- **核心问题**：① 父类优先遍历顺序如何导致「写入污染父类包」？② `_C` / `_GEN_VARIABLE` 两个后缀各在什么 API 边界出现？③ 为什么纯原生 C++ Actor 类进不了 SCS 分支？④ `GetActualComponentTemplate(BPGC)` 与裸模板指针的差异？
- **源码入口**：`EditorGetComponentWithGameplayTag`(:1070–1133，三段式) 与 `EditorGetOrCreateComponentTemplateForWrite`(:1136–1233，写路径) 对照；`SpawnComponentToDefaultEntity`(:1361–1435，SCS->CreateNode/AddNode + `_C` 剥离 :1370–1373)；`GetEntityComponentNames`(:1577，去 `_GEN_VARIABLE` :1597–1601)；`GetAllStaticMeshesFromBlueprintClass`(:4852)/`GetAllSkeletalMeshesFromBlueprintClass`(:4925，CDO+SCS 双通道，`GetActualComponentTemplate` 注释 :4904 区域)；`Main/Plugins/PLPythonPipeline/references/component-template-inheritance.md` 全文；引擎 `Engine/Source/Runtime/Engine/Classes/Engine/SCS_Node.h` / `SimpleConstructionScript.h` / `InheritableComponentHandler.h`（注意在 Classes 不在 Public）。
- **PLPythonPipeline·AS 对照案例**：写路径归属校验 `GetTypedOuter<UBlueprintGeneratedClass>()` + `UInheritableComponentHandler::CreateOverridenComponentTemplate(FComponentKey)`（:1186–1213）；AS 侧 `EditorGetComponentWithGameplayTag` 调用（as:297/699）与 Python 直连（`da_temperature_payload_processor.py:61/133/166/173`）。
- **最小实验**：对一个「父 BP 加组件、子 BP 未覆写」的继承链调 `EditorGetComponentWithGameplayTag`，打印返回组件的 `GetTypedOuter<UBlueprintGeneratedClass>()`；再用写路径版拿 override 模板，确认 outer 变为子类 BPGC。
- **产出物与验收标准**：能回答核心问题①–④；产出「读路径 vs 写路径」组件模板决策卡。
- **预计课次**：2

#### C22 DataTable 行 ↔ 资产写回 与 dry-run 纪律（v1 C12）

- **学习目标**：DataTable 反射面（行内存即结构体内存）；行→DataAsset/组件/CDO 的三条写回链；GC 防护；dry-run 的「只比不写 + 计数上报 + 副作用还原」纪律（C8 应用经验的机制层精读）。
- **核心问题**：① 行内存在反射层被当作什么（`void*` container）？② `TSoftClassPtr→TSubclassOf` 的转换在 `ConvertAndSetPropertyValueEx` 哪一段？③ `AddToRoot`+RAII RootGuard 在防什么？④ dry-run 为什么要监听 `UPackage::PackageMarkedDirtyEvent` 再还原？⑤ dry-run 下读到旧 DT 时新增行的 Warning 为何是预期输出？
- **源码入口**：`SetEntityComponentPropertiesFromDataTable`(:807–1069 主编排范式；GC 防护 :863–880)；`CopyPropertiesFromDataTableRow`(:295–345)；`SetEntityPropertiesFromDataTable`(:635–806 软引用特判段)；`ApplyBodyInstancePropertiesFromDataTable`(:1235，嵌套结构体寻址)；`SpawnOrRemoveAuraComponentToSingleEntityFromDataTable`(:2704，`GetRowMap()` 结构化绑定遍历 + `reinterpret_cast` 行内存)；dry-run 计数三件套 `ResetDryRunMismatchCounts`(:4470)/`AddDryRunMismatchCount`(:4475)/`GetDryRunMismatchCounts` + `namespace DryRunMismatchKeys`(:93)；`ProcessPropertyName`(:3364)。
- **PLPythonPipeline·AS 对照案例**：端到端调用链 `Excel → excel_exporter.py::generate_all() → RunEntityTagMappingRow(AS) → PLPythonAutomation::* (C++) → UE 反射层`（as:174/297/449/461/468/476/477；exporter 侧 `excel_exporter.py:370`）；dry-run 退出码语义与 CI 日志纪律（`Main/Plugins/PLPythonPipeline/SKILL.md` + `references/troubleshooting.md` §1.11）。
- **最小实验**：构造一行与资产现值不同的 DT 行，`IsDryRun=true` 跑一遍读 LogW 的 Current/Expected，再 `false` 跑一遍确认 `MarkPackageDirty`；观察 dry-run 计数 key。
- **产出物与验收标准**：能回答核心问题①–⑤；产出 dry-run 纪律清单（沉淀为表 J 素材）。
- **预计课次**：2

#### C23 资产生成、写后通知与 JSON 互转（v1 C13）

- **学习目标**：`IAssetTools::CreateAsset` + 工厂分支；写后三件套；`UEngine::CopyPropertiesForUnrelatedObjects` vs 手写 CopyPropertiesByName 的取舍；`FJsonObjectConverter` 双向互转在资产对账中的应用。
- **核心问题**：① `UDataAssetFactory` 与 `UBlueprintFactory` 的选择依据？② `MarkBlueprintAsStructurallyModified` 与 `PostEditChangeProperty` 各自触发什么？③ JSON 互转的精度/大小写陷阱（`SkipStandardizeCase`）？④ 为什么 WaterBody 迁移不用引擎 Replace 而手写按名拷贝（.h 头注的设计权衡）？
- **源码入口**：`CreateAssetsFromDataTable`(:1766–1830 工厂分支 + :1832–1865 dry-run 脏包还原)；`CreateAssetFromDataTableSingleRow`(:2094)；`SetEditorObjectProperty`(:3825，写后三件套 :3904–3922)；`Utils/PLBlueprintComponentFixupLibrary.cpp` 全文件（SCS 换类手术 + `ExportText_Direct` 全属性 dump 对账 :235–245 + `CopyPropertiesForUnrelatedObjects` :152–158）；JSON 四函数 `ConvertStructToJsonString`(:4532)/`ConvertJsonStringToStruct`(:4564)/`ConvertUObjectToJsonString`(:4661)/`ConvertJsonStringToUObject`(:4671)；Python 对账侧 `Content/Python/utils/unreal_util.py:767/792`。
- **PLPythonPipeline·AS 对照案例**：`RunEntityTagMappingRow` 内 `CreateAssetsFromDataTable`（as:174）是资产创建主入口；`entity_modifier.py:477` 的 Python 直连写回路径。
- **最小实验**：用 `CreateAssetFromDataTableSingleRow` 对不存在的路径创建资产，再对存在路径走 LoadAsset+CheckoutAsset 分支；对比两次日志。
- **产出物与验收标准**：能回答核心问题①–④；产出「写后通知三件套」使用时机表。
- **预计课次**：1–2

#### C24 负结论与对照组（UFunction / 二进制反射）（v1 C14）

- **学习目标**：明确两个「没有」——PLPythonPipeline 没有 `ProcessEvent` 动态调用、不依赖运行时反射调函数；live FProperty 反射与 `FPropertyTag` 二进制解码的前提差异。
- **核心问题**：① 本插件为什么没有 `ProcessEvent`？（提示：调用方是 AS/Python，绑定在编译期完成）② live FProperty 反射与 FPropertyTag 二进制解码各自的前提（对象已加载 vs 不加载）？③ UFunction 以「数据」身份出现的两个场景（造 K2 节点模板、委托绑定）？
- **源码入口**：`Utils/EditorExBPLibrary.cpp:290–320`（`FindFieldChecked<UFunction>` 造节点）；`Private/UAssetSemantic/PLPropValueDecoder.cpp`（刻意 0 反射命中，头 80 行）+ `PLUassetDissector.cpp`（2018 行二进制侧）；`Main/Plugins/PLPythonPipeline/references/uasset-dissector.md`；引擎 `CoreUObject/Private/UObject/PropertyTag.cpp` `FPropertyTag`。
- **PLPythonPipeline·AS 对照案例**：用 ue-cli/编辑器 Python 调一个本插件 UFUNCTION（体验静态绑定），再读 `UKismetSystemLibrary::StaticClass()` 上 `FindFieldChecked` 造节点的代码，对照两者差异。
- **最小实验**：同上对照案例即实验；再用 dissector dump 一个含 TMap 属性的 uasset，对照 live 反射读出的同属性值。
- **产出物与验收标准**：能回答核心问题①–③；能一句话说清「什么时候必须走二进制解码」。
- **预计课次**：1

---

### Phase F — 热更新四系统（L4 课程重心）

#### C25 四系统对照总览（纯心智模型章）（v1 C15）

- **学习目标**：用九个维度建立 Live Coding / 旧 HotReload / BP Reinstancing / AS Reload 的对照矩阵：触发源 / 编译产物 / 是否替换 UClass / 旧类处置 / 活体实例迁移 / PIE 中行为 / 布局变更容忍度 / 失败回滚 / 运行线程。
- **核心问题**：① 四个系统各自「替换什么、保留什么」？② 哪些维度组合决定「改函数体安全、改布局危险」？③ 四套系统两两之间有哪些已知的触发/互斥边？
- **源码入口**：无新源码——本章只组织 C0 的图与后续四章的入口预告。
- **PLPythonPipeline·AS 对照案例**：设想「改 `PLPythonAutomationFunctionLibrary.cpp` 一个函数体」「给某 AS 类加 UPROPERTY」「改实体 BP 默认值」三个场景，预判各落入哪个系统（C5 已有现象经验）。
- **最小实验**：把上述三个场景写入九宫格，C26–C29 学完后回填验证。
- **产出物与验收标准**：产出四系统九维对照表（表 C）骨架；验收在 C30 末统一进行。
- **预计课次**：1

#### C26 C++ Live Coding（v1 C16）

- **学习目标**：`FLiveCodingModule::Compile` → LPP patch → `FReload(EActiveReloadType::LiveCoding)` → `ProcessNewlyLoadedUObjects` → `NotifyFunctionRemap` → `UFunction::SetNativeFunc` 重映射 → `FReload::Reinstance`（CDO/实例）→ Finalize 全链。
- **核心问题**：① 为何改函数体安全、改反射布局危险？② Func 指针是在哪一刻被换掉的？③ patch 与整 DLL 重绑的本质差异？
- **源码入口**：`Engine/Source/Developer/Windows/LiveCoding/Private/LiveCodingModule.cpp` `Compile`（约 :246）/`FNullReload`（约 :63）/patch 后序列（约 :825–854）；`Engine/Source/Runtime/CoreUObject/Public/UObject/ReloadUtilities.h` `class FReload : public IReload`（约 :15）；`ReloadUtilities.cpp` `NotifyFunctionRemap`（约 :918）/`Reinstance`（约 :1020）/`Finalize`（约 :1183）；`CompiledInUObjectInit.cpp` `ProcessNewlyLoadedUObjects`（约 :84）。（以上行号待复核）
- **PLPythonPipeline·AS 对照案例**：改 `PLPythonAutomationFunctionLibrary.cpp` 某函数体 → patch 后 AS 侧调用立即生效；但新增 UFUNCTION 后 AS 绑定为何不刷新（铺垫 C30）。
- **最小实验**：改一个 cpp 函数体 → Live Coding patch 观察日志；改头文件布局观察失败/警告模式。
- **产出物与验收标准**：能回答核心问题①–③；回填 C25 九宫格对应行。
- **预计课次**：1–2

#### C27 旧 HotReload（遗产路径）（v1 C17）

- **学习目标**：`FHotReloadModule::DoHotReloadFromEditor`/RebindPackages 整 DLL 重绑路径；经 `FCoreUObjectDelegates` 两个 Reinstancing delegate 做类替换；与 Live Coding 的互斥。
- **核心问题**：① 它与 Live Coding 的本质差异（整 DLL 重绑 vs patch）？② 为何没落（工具链/布局容忍/迭代速度）？③ 本分支它还有没有真实触发面？（属已知未知项，正文化前需确认）
- **源码入口**：`Engine/Source/Developer/HotReload/Private/HotReload.cpp` `DoHotReloadFromEditor`（约 :539–556）/:760/:783/:884/:1052/:1074；`UObjectGlobals.cpp` `RegisterClassForHotReloadReinstancingDelegate`/`ReinstanceHotReloadedClassesDelegate`（约 :184–185）；互斥点 `LevelEditorActions.cpp` 的 "NoLiveCodingCompileAfterHotReload"（约 :1501）。（行号待复核）
- **PLPythonPipeline·AS 对照案例**：无直接对照；作为「AS Reload 出现之前 UE 怎么做类替换」的历史对照，帮助理解 C29 的设计选择。
- **最小实验**：通读 `DoHotReloadInternal` 一遍；在项目里确认它还会被谁触发（大概率仅 IDE 集成遗留）。
- **产出物与验收标准**：能回答核心问题①②；对③给出有证据的结论或标注未知。
- **预计课次**：1

#### C28 Blueprint Reinstancing（v1 C18）

- **学习目标**：`FBlueprintCompileReinstancer` 全流程：旧类搁置（`CLASS_NewerVersionExists`）/字段映射/实例批量替换/CDO 迁移顺序/字节码引用更新；本分支 HAZE 与 @CYANCOOK 补丁群各防什么事故。
- **核心问题**：① 「旧对象不删、指针替换」策略的对象生命周期依据？② CDO 迁移顺序为何敏感（`UpdateBytecodeReferences` 必须在 `PropagateValuesToCDO` 之后）？③ HAZE 补丁群（跳过 AS 类 relink、子类 reparent、重复调用防护、struct 同 pass 替换、ScriptTypePtr 复制、组件引用、挂载修复）各防什么？④ @CYANCOOK 的 DuplicateDataReader 跨图引用拦截如何影响 reinstancer 的复制语义？
- **源码入口**：`Engine/Source/Editor/UnrealEd/Private/Kismet2/KismetReinstanceUtilities.cpp` `GenerateFieldMappings`(:674)/`ReinstanceObjects`(:1006)/`UpdateBytecodeReferences`(:1224)/`BatchReplaceInstancesOfClass`(:1941/:1974)；HAZE 补丁位（约 :1970/:2170/:2490/:2523/:2642/:2655/:2661/:2677，待复核）；AS FIX :2960 区域（字节码引用顺序，待复核）；`ScriptCore.cpp:1394` 附近 `DO_BLUEPRINT_GUARD` 拦截（待复核）；`BlueprintCompilationManager.cpp` `ReinstanceBatch`(:2781)；@CYANCOOK 点 `DuplicateDataReader.cpp`（约 :13/:82）与 `BlueprintCompilationManager.cpp`（约 :3455/:3519）。
- **PLPythonPipeline·AS 对照案例**：被 C21 写过的实体 BP（SCS 覆写模板、CDO 默认值）在 reinstance 时正是「活体实例迁移」的对象；`RefreshAndCompileBlueprint` 触发的编译也会走本链。
- **最小实验**：改一个 BP 触发编译，观察 OldClass(REINST_)/`CLASS_NewerVersionExists` 与实例迁移日志。
- **产出物与验收标准**：能回答核心问题①–④；产出「reinstance 事故 → 防护补丁」对照卡。
- **预计课次**：2–3

#### C29 AngelScript Reload（soft vs full）（v1 C19）

- **学习目标**：文件时间戳轮询 → debounce → Tick 分流 → PerformHotReload → 三级重载需求判定 → SwapInModules → PerformReload → InitDefaultObjects → ClassReloadHelper 收尾（**AS 与 BP 两大热更新系统的交汇点**；C5 现象全收的机制章）。
- **核心问题**：① Soft/FullReloadSuggested/FullReloadRequired 三级判定的触发条件？② 为何 PIE 中 full 需求降级为 soft+警告、退出 PIE 后补做？③ `ClassReloadHelper` 如何把「AS 类被替换」传染给引用它的 BP（FArchiveReplaceObjectRef → ReparentHierarchies → OnObjectsReinstanced → QueueForCompilation → FlushCompilationQueueAndReinstance）？④ 热更后自动跑 HotReloadTestRunner 的意义？
- **源码入口**：`AngelscriptManager.cpp` `StartHotReloadThread`（约 :574）/`CheckForHotReload`(:1480)/`Tick`(:1549，:1579/:1583 分流)/`PerformHotReload`（约 :1160）/`SwapInModules`（约 :1651）/判定 switch（约 :2600–2697）；`AngelscriptClassGenerator.cpp` 需求升级规则（约 :168–173）/`ShouldFullReload`(:2091)/`PerformReload`(:2116)/`InitDefaultObjects`(:5828)/@CYANCOOK CDO 检查钩子（约 :2292）；`AngelscriptEditor/Private/ClassReloadHelper.cpp` `PerformReinstance`(:24)/:143/:187–189（ReparentHierarchies + OnObjectsReinstanced）/:304–311；程序触发热更入口 `FAngelscriptManager::FileChangesDetectedForReload`（`AngelscriptManager.h:345`）。
- **PLPythonPipeline·AS 对照案例**：改 `DataTableRowProcessor_PLEntityTagMapping.as` 函数体 → soft reload；给它加 UPROPERTY → full reload；dry-run 链路（C22）在 reload 后是否立即可用。
- **最小实验**：① 改函数体 → soft reload；② 加 UPROPERTY → full reload；③ PIE 中做②，观察排队行为与警告（C5 实验的机制复跑）。
- **产出物与验收标准**：背出 soft/full 判定条件（沉淀为表 E）；解释「PIE 里新属性不出现」为何是设计行为而非 bug。
- **预计课次**：2–3

#### C30 四系统交互与冲突（综合章）（v1 C20）

- **学习目标**：跨系统连锁与互斥的全景：AS reload → BP recompile 链；Live Coding 后 AS 绑定不刷新；CDO 构建线程约束；GC 约束；挂起协程与热重载取消钩子。
- **核心问题**：① 新 UFUNCTION 为什么必须重启编辑器才对 AS 可见（绑定只在启动生成——C4/C5 现象的机制答案）？② `default{}` 禁同步加载的机制根因（InitDefaultObjects 跑在 TaskGraph worker 线程、ZenLoader 不能 FlushAsyncLoading——C2 现象的机制答案）与静态检查器 `ValidateConstructionBlockingLoads` 的日志抓手 `[ASConstructionLoad]`？③ 为何禁增量 GC（`checkf gc.AllowIncrementalReachability`）？④ 跨系统故障的排查决策树第一刀切在哪（先判层，再判哪个热更新系统）？
- **源码入口**：`ClassReloadHelper.cpp` 全链（C29）；`AngelscriptClassGenerator.cpp` `ValidateConstructionBlockingLoads`（约 :5615–5824）；`AngelscriptManager.cpp:263`（增量 GC checkf）；PLScriptAsync 的 OnPostReload/OnWorldCleanup 取消钩子——⚠️ **该插件 head 只有 SKILL.md，实现在未提交 shelf 119677/117988**，本章按 SKILL 不变量文档学习并显著标注「代码待 rebase」（见已知未知项）。
- **PLPythonPipeline·AS 对照案例**：给 `PLPythonAutomationFunctionLibrary` 新增一个 UFUNCTION 后，分别尝试 Live Coding / AS reload / 重启编辑器三条路径，验证只有最后一条让 AS 可见（本实验即 C32 的预演）。
- **产出物与验收标准**：产出跨系统故障排查决策树（判层 → 判系统 → 判维度）；能回答核心问题①–④；回填表 C 完成 L4 验收。
- **预计课次**：2

---

### Phase G — AS L5 扩展与修改（渐进修改阶梯）

> 进入本篇要求 L4 退出达成。七级阶梯**顺序刚性**，每级注明「最小安全修改边界 / 验证方式」，**不给实现答案**；每级完成后回填表 L。纪律提醒：改 `Engine/Plugins/Angelscript` 任何代码必须 `@CYANCOOK` 包裹；改 `ThirdParty/` 必须先进 `E:\angelscript-merge` vendor 仓再同步（见 `Engine/Plugins/Angelscript/SKILL.md` 与 `ThirdParty/SKILL.md`）。

#### C31 L5-1 新增一个 AS 使用案例（纯项目层改动）

- **学习目标**：把「修改」的仪式感降到最低——第一级只允许新增 `.as`，验证全链路观测手段已就位。
- **前置/进入标准**：L1–L4 退出达成（形式上加固：本级的真实目的是验证 C38 观测工具箱已能熟练使用）。
- **核心问题**：① 新增一个 AS 类时哪些决定影响 reload 需求级别（命名、属性、继承）？② 如何证明「新类已被编译且行为正确」而不只靠肉眼？
- **源码/案例入口**：`Main/Script/Tests/1000_RuntimeTests/PLAutomationSampleCase.as`（参照范式）；`Main/Script/Utilities/`（落点目录）。
- **最小安全修改边界**：只新增 `Main/Script/` 下的 `.as` 文件；不改任何 C++/引擎/插件；目录命名避开 `Dev`/`Editor`。
- **验证方式**：热更日志无 Error → `AS.ListScripts` 可见新类 → 配套 PLAutomation 最小用例（`ue-cli run-plauto --filter`）通过。
- **产出物与验收标准**：新类 + 用例入库级质量（可提交标准，但本课程不执行提交）；表 L 第 1 行回填。
- **预计课次**：1

#### C32 L5-2 新增 / 修复 C++ 自动绑定可见性

- **学习目标**：理解「UFUNCTION 对 AS 可见」的完整前提链；学会只改项目层 C++ 声明来修复/新增绑定。
- **核心问题**：① 一个 UFUNCTION 从声明到 AS 可调，中间经过哪些生成物（.gen.cpp 的 ASFunctionPointers → 启动期绑定 → Binds.Cache）？② 哪些 UCLASS/UFUNCTION specifier 影响 AS 可见性？③ 为什么 Live Coding patch 后 AS 仍不可见（C26/C30 结论的运用）？
- **源码/案例入口**：`Main/Plugins/PLPythonPipeline/.../PLPythonAutomationFunctionLibrary.h`（练手宿主）；`Helper_FunctionSignature.h:100–127`（命名规则把关点）。
- **最小安全修改边界**：只改**项目自有插件**（`Main/Plugins/*`）的 UCLASS/UFUNCTION/UPROPERTY 声明（新增或调整 specifiers）；不动 `Engine/` 与 `Engine/Plugins/Angelscript`。
- **验证方式**：重启编辑器（绑定只在启动生成，C30 结论）→ AS 侧调用打通 → `AS.DumpBindings` 出现新条目 → 既有 PLAutomation 套件回归通过。
- **产出物与验收标准**：一个真实新增的 UFUNCTION 及其 AS 消费端；产出「绑定可见性前提链」图；表 L 第 2 行回填。
- **预计课次**：1–2

#### C33 L5-3 手写 Bind_* 扩展

- **学习目标**：读懂手写绑定层（相对 126 个自动绑定 `Bind_*.cpp`）的角色；新增一个最小的手写绑定。
- **核心问题**：① 自动绑定覆盖不到的场景有哪些（容器模板特化、全局函数、命名空间整形）？② `AngelscriptBinds.h` 的注册宏序列是怎么被 BindDatabase 消费的？③ 手写绑定如何影响 Binds.Cache 的内容？
- **源码/案例入口**：`Public/AngelscriptBinds/Bind_TArray.h`（容器模板范本）；`Private/Binds/Bind_FGameplayTag.cpp:40–59`（`GameplayTags::` 全局量注册范本——C7 现象的机制答案）；`Private/Binds/Bind_BlueprintCallable.cpp`。
- **最小安全修改边界**：在 `Engine/Plugins/Angelscript` 内**新增**一个 `Bind_*.cpp`（不改动既有 126 个）；全程 `@CYANCOOK` 包裹；不触碰 `ThirdParty/`。
- **验证方式**：触发 Binds.Cache 重建 → 写一个消费该绑定的 `.as` 冒烟脚本跑通 → 回滚后确认缓存失效路径符合预期。
- **产出物与验收标准**：一个最小手写绑定 + 冒烟脚本；能说清它为什么不能用自动绑定替代；表 L 第 3 行回填。
- **预计课次**：1–2

#### C34 L5-4 理解 / 修改 UASClass 与 UASFunction 生成

- **学习目标**：在类生成器里做一处有界改动，理解 Desc → UClass/UFunction 的生成路径与 reload 需求分级判定的耦合。
- **核心问题**：① `FAngelscriptClassGenerator` 各生成函数的调用序与失败恢复？② reload 需求升级规则（约 :168–173）为什么长这样——改动它会误伤什么？③ CDO 检查钩子（@CYANCOOK，约 :2292）插在哪个时机、为什么？
- **源码/案例入口**：`AngelscriptClassGenerator.cpp` `AddModule`(:62)/`ShouldFullReload`(:2091)/`PerformReload`(:2116)/`InitDefaultObjects`(:5828)；`ASClass.h`（约 :124–219）。
- **最小安全修改边界**：`AngelscriptClassGenerator.cpp` 内**单个生成函数**的有界改动（@CYANCOOK 包裹）；不改 T2 引擎头（`Class.h`/`Script.h`）；不改 ThirdParty。
- **验证方式**：改动后跑 HotReloadTestRunner（热更后自动测试钩子，C29）→ 对一个带新特性的 AS 类做 full reload → CDO 检查钩子无报警 → `AS.ListScripts` 与 FunctionFlags 抽查。
- **产出物与验收标准**：一处有界生成器改动 + 改动理由书（写清「不这么改会怎样」）；表 L 第 4 行回填。
- **预计课次**：2

#### C35 L5-5 修改 UE↔AS RuntimeCall 桥（T2 引擎补丁层）

- **学习目标**：理解 T2 补丁层的最小切面；在 `AS FIX(LV)` 块内做一处有界改动。
- **核心问题**：① `RuntimeCallFunction`/`RuntimeCallEvent` 的 40 个特化各自按什么维度切分（返回类型/参数形态/NetValidate）？② 改桥接层为什么会同时影响 BP 调用 AS、replicator、以及 reinstancing？③ NetValidate 路径与本地路径的分叉点在哪？
- **源码/案例入口**：`ScriptCore.cpp` :1154/:1203–1217/:1356/:2114+/:2147–2215；`ASClass.cpp` `AngelscriptCallFromBPVM`（约 :105；:1918 起特化群）；`Class.h` T2 字段区。
- **最小安全修改边界**：只改 `AS FIX(LV)` 注释块**内部**；必须同步检查 40 个 RuntimeCallFunction 特化与 NetValidate 路径是否受波及；任何 T2 改动默认视为高风险，先在分支上隔离。
- **验证方式**：BP↔AS 双向调用断点回归（C13 实验复跑）→ PLAutomation 全套 → Development 包 smoke（确认 `FUNC_RuntimeGenerated` 路径在 cooked 构建仍通）。
- **产出物与验收标准**：一处 T2 有界改动 + 波及面分析（列出所有被检查的特化）；表 L 第 5 行回填。
- **预计课次**：2

#### C36 L5-6 修改编译阶段 / ThirdParty VM

- **学习目标**：理解 `CompileModules` 分阶段序列的不可乱序性；了解 vendor fork 的修改纪律。
- **核心问题**：① 为什么 defer 标志的设置/还原时机不能动（:1827/:2415）？② `asCModule::Build()` 空壳化后，所有「自定义编译」为什么必须复刻 Manager 序列？③ ThirdParty 的修改为什么要先进 `E:\angelscript-merge` 再同步？
- **源码/案例入口**：`AngelscriptManager.cpp` `CompileModules`(:1798) 全序列（C11 已读）；`ThirdParty/SKILL.md`（vendor 纪律与 fork 契约）；`ThirdParty/source/as_module.cpp` `Build()` 空壳（约 :290）。
- **最小安全修改边界**：优先只做「编译阶段编排层」的改动（Manager 侧，@CYANCOOK 包裹）；ThirdParty 本体改动属于最高风险级——本课程只要求能按纪律走通流程，不要求实际改 VM。
- **验证方式**：`-as-ignore-precompiled-data` 全量重编译通过 → headless `AngelscriptAllScriptRoots` commandlet（C5/C9 手段）通过 → Development 包运行时编译 smoke。
- **产出物与验收标准**：编译阶段改动（或 VM 修改流程演练记录）+ 分阶段序列检查单；表 L 第 6 行回填。
- **预计课次**：2–3

#### C37 L5-7 设计 reload / reinstancing 回归测试

- **学习目标**：为前六级修改设计回归防护——修改阶梯的最后一环是「让未来的修改更安全」。
- **核心问题**：① HotReloadTestRunner 的钩子时机决定了它能抓住哪类回归、抓不住哪类？② 哪些 reload/reinstancing 事故只能被「布局改动 + 活体实例」组合测试抓住？③ 如何把 C39 故障案例库的每个案例转化为一条可自动跑的回归？
- **源码/案例入口**：HotReloadTestRunner 钩子在 `PerformHotReload` 收尾段（C29 锚点链内）；`Main/Script/Tests/` 分层（C9）；C28 的「reinstance 事故 → 防护补丁」对照卡。
- **最小安全修改边界**：只新增测试资产与用例（`Main/Script/Tests/` + 测试钩子配置）；不改被测系统本体。
- **验证方式**：故意引入一处 soft 类改动与一处 full/布局类改动，验证新测试能分别捕获；再用干净工作区验证不误报。
- **产出物与验收标准**：一组 reload/reinstancing 回归用例 + 覆盖矩阵（事故类型 → 用例）；表 L 第 7 行回填；至此 L5 退出达成。
- **预计课次**：1–2

---

### Phase H — 可观测工具箱 + 综合排障实训（贯穿）

#### C38 观测工具箱（sidecar，全程伴随）（v1 C21）

- **学习目标**：把「看」的手段配齐：日志频道、控制台命令、命令行开关、调试断点推荐位、自动化入口。
- **核心问题**：① 每类问题最先看哪个日志频道/命令？② unattended/commandlet 下脚本编译失败退出码为何可能是 0（日志污染判读）？③ 断点该下在哪几个「咽喉位」？
- **源码入口**：日志 `LogAngelscript`/`LogScriptCore`；控制台 `AS.ReloadAll`/`AS.ListScripts`/`AS.DumpBindings`；命令行 `-as-development-mode`/`-as-simulate-cooked`/`-as-ignore-precompiled-data`/`-asdebugport=`；headless 编译验证 `-run=AngelscriptAllScriptRoots -as-force-preprocess-editor-code`；断点推荐位表（`ProcessEvent`/`Invoke`/`ProcessInternal`/`AngelscriptCallFromBPVM`/`PerformReload`/`FReload::Reinstance`）；测试入口 `ue-cli run-plauto`（PLAutomation AS 用例，filter 规则：前缀 `PLAutomation.`）。
- **PLPythonPipeline·AS 对照案例**：dry-run 报告的 CI 可见性纪律（`unreal.log_warning`/`unreal.log_error` vs Log 级丢失）作为「观测渠道选择」的真实案例。
- **最小实验**：给每个断点推荐位各下一次断点并记录命中场景。
- **产出物与验收标准**：产出观测抓手速查表（表 I）；验收贯穿后续所有章节实验（从 Phase A 起强制使用）。
- **预计课次**：1（sidecar，不计入主链节奏）

#### C39 故障案例库 / 综合排障实训（v1 C22）

- **学习目标**：用真实故障案例串起全部章节；每案按「症状 → 定位路径 → 根因 → 修复原则」四段式演练。
- **核心问题**（案例清单，全部来自真实记录）：
  1. C++ 函数脚本里找不到 → 前缀剥离 + @CYANCOOK 属性同名回退（`Helper_FunctionSignature.h:100–127`）
  2. cooked 与编辑器行为不一致 → Binds.Cache/PrecompiledScript 过期，`-as-simulate-cooked` 复现
  3. "ZenLoader unable to FlushAsyncLoading" → `default{}` 同步加载（堆栈含 `UASClass::StaticObjectConstructor`+`InitDefaultObjects`）
  4. 启动 checkf → 增量 GC 未关
  5. 自动化「成功」但脚本没编译 → unattended 编译失败退出码 0
  6. BP 事件图遮蔽 AS BlueprintOverride（ReceiveBeginPlay 静默不执行）
  7. dry-run 退出码 3000/3001 的 A/B/C 分类判读（PLPythonPipeline troubleshooting §1.11）
  8. 测试报错白名单纪律：只修根因，严禁 `SuppressLogErrors` 扩白名单（CLAUDE.md §7）
  9. （v2 新增）`namespace GameplayTags` 变量名与自动绑定冲突 → 5674 条 `Name conflict`（`Main/Script/Editor/SKILL.md` Troubleshooting；机制在 `Bind_FGameplayTag.cpp:40–59`）
  10. （v2 新增）AS 裸构造 C++ 类失败（"Data type can't be ..."）→ 非可实例化绑定，走 builder/工厂（`PLAutomationSampleCase.as` 头注释实录）
- **源码入口**：各案例对应前序章节入口。
- **PLPythonPipeline·AS 对照案例**：案例 7 即 PLPythonPipeline 本体；案例 1/5 以其 UFUNCTION 为素材。
- **最小实验**：每案独立复现一次（能复现的）+ 写出四段式分析。
- **产出物与验收标准**：10 份四段式故障分析卡；随机抽 3 案能口头推演定位路径。
- **预计课次**：2

---

## 3. 总进度 checkbox

```
Phase 0 全局地图
- [ ] C0  三套生产链、五层实体、AS 五级阶梯与四套热更新地图 (1 课次)
Phase A — AS L1 日常使用（会用）
- [ ] C1  AS 脚本目录与模块发现 (1)
- [ ] C2  第一个 AS 类：类/属性/函数/default/构造与生命周期 (1-2)
- [ ] C3  常用宿主模式：Actor/Component/UObject/Subsystem (1)
- [ ] C4  调用 C++：UFUNCTION 与反射属性访问 (1)
- [ ] C5  日常迭代工作流：soft/full reload 与日志入门 (1)
      ── L1 退出验收 ──
Phase B — AS L2 应用模式（会组织）
- [ ] C6  BlueprintEvent/BlueprintOverride 与 BP↔AS 协作 (1-2)
- [ ] C7  容器/委托/定时器/GameplayTag/资产与软引用 (2)
- [ ] C8  DataTable 与 PLPythonPipeline 编辑器自动化 (1-2)
- [ ] C9  调试/日志/自动化测试 (1-2)
- [ ] C10 （可选/未知）网络复制、协程与异步 (0-1)
      ── L2 退出验收 ──
Phase C — AS L3 行为到原理映射
- [ ] C11 AS 编译管线与模块加载 (2)
- [ ] C12 类型与函数注册 .as→UASClass (2)
- [ ] C13 双向桥接 UE↔AS (2)
- [ ] C14 AS 运行时执行环境 (1-2)
      ── L3 退出验收（≥10 条现象→机制映射）──
Phase D — Epic 通用底座（L4 地基）
- [ ] C15 C++↔反射链对齐 5.8 (1-2)
- [ ] C16 Blueprint VM 运行时 (2)
- [ ] C17 Kismet 编译管线 (2)
Phase E — PLPythonPipeline 真实反射用例
- [ ] C18 FProperty 查找与类型判定 (1)
- [ ] C19 值读写三件套与先比后写 (1)
- [ ] C20 容器属性运行时操作 (1-2)
- [ ] C21 BPGC/SCS/CDO/组件模板 (2)
- [ ] C22 DataTable 行↔资产写回与 dry-run (2)
- [ ] C23 资产生成、写后通知与 JSON 互转 (1-2)
- [ ] C24 负结论与对照组 (1)
Phase F — 热更新四系统
- [ ] C25 四系统对照总览 (1)
- [ ] C26 C++ Live Coding (1-2)
- [ ] C27 旧 HotReload 遗产路径 (1)
- [ ] C28 Blueprint Reinstancing (2-3)
- [ ] C29 AngelScript Reload soft/full (2-3)
- [ ] C30 四系统交互与冲突 (2)
      ── L4 退出验收（表 C/D/E 回填完成）──
Phase G — AS L5 扩展与修改（渐进修改阶梯）
- [ ] C31 L5-1 新增一个 AS 使用案例 (1)
- [ ] C32 L5-2 新增/修复 C++ 自动绑定可见性 (1-2)
- [ ] C33 L5-3 手写 Bind_* 扩展 (1-2)
- [ ] C34 L5-4 理解/修改 UASClass/UASFunction 生成 (2)
- [ ] C35 L5-5 修改 UE↔AS RuntimeCall 桥 (2)
- [ ] C36 L5-6 修改编译阶段/ThirdParty VM (2-3)
- [ ] C37 L5-7 设计 reload/reinstancing 回归测试 (1-2)
      ── L5 退出验收（表 L 七行回填完成）──
Phase H 观测与排障（贯穿）
- [ ] C38 观测工具箱 sidecar (1)
- [ ] C39 故障案例库/综合排障 (2)
```

合计约 **54–62 课次**（每课次 60–90 分钟；v1 为 35–40，增量全部来自 AS 应用篇与 L5 修改阶梯——**AngelScript 篇幅显著提升是有意为之，不为控制总章数压缩**）。

## 4. 依赖图

```
C0 ──→ 所有章节（图例 + 阶梯定义）

【先浅：应用篇】
C0 ──→ C1 → C2 → C3 → C4 → C5                     （L1 链，顺序基本刚性）
C2+C4 ──→ C6 → C7 → C8 → C9                       （L2 链；C10 可选，不阻塞）
C38：sidecar，自 Phase A 起全程伴随，不阻塞任何章节

【后深：机制与源码篇】
L1+L2 完成 ──→ C11 → C12 → C13 → C14              （L3 机制；C15 为 C12/C13 软依赖，可插读）
C15 ──→ C16 ──→ C17                               （L4 地基，建议与 Phase C 并行）
C15+C16 ──→ C18 → C19 → C20 → C21 → C22 → C23 → C24   （Phase E 硬依赖仅 C15+C16，可与 Phase C 交错）
C25 ──→ C26 ──→ C27                               （对照组先行）
C17 ──→ C28                                       （编译管线的续章）
C12+C16 ──→ C29                                   （AS 注册 + VM 底座）
C26~C29 ──→ C30                                   （综合章）

【能修改：L5 阶梯】
L4 退出达成 ──→ C31 → C32 → C33 → C34 → C35 → C36 → C37   （顺序刚性）
全部 ──→ C39                                       （收尾实训）
```

阶梯提示：L1/L2 是最快的正反馈区（每天都写得出东西）；C28/C29/C34–C36 最难、留足课次；C10 证据不足，允许长期挂起。

## 5. 建议节奏

- **节奏**：每周 2–3 课次，全程约 **20–26 周（5–6.5 个月）**（v1 为 14–18 周；延长是有意为之）。宁慢勿快——每章的「产出物」不齐不进下一章，每级的「退出标准」不齐不进下一级。
- **顺序**：主链按 Phase 0 → A → B →（C 与 D 交错）→ E → F → G → H 收尾；Phase E（C18–C24）硬依赖仅 C15+C16，可与 Phase C 交错缓解纯引擎阅读的疲劳。
- **回顾点**：每个 Phase 末留 0.5–1 课次回填对照表（表 A–M）并口述验收；每个阶梯末（L1–L5）做一次正式退出验收。
- **sidecar**：C38 从 Phase A 起全程伴随，实验中强制使用。
- **正文化规则**（待确认）：每章正文遵循「原文逐段解剖 + 锚点链接、细节后置分类、值类型化渲染」的报告审美（团队既有约定），行号以符号为主锚点。

## 6. 关键对照表清单（正文阶段产出）

| 表 | 主题 | 归属章节 | 用途 |
|---|---|---|---|
| 表 A | 机制 → 四层归属（T1–T4）速查（机制/标记/代表文件） | C0 | 排障第一刀 |
| 表 B | 三套生产链对照（C++ native / BP / AS：产物、执行体、热更新系统） | C0/C15 | 全局地图 |
| 表 C | 四套热更新系统九维对照 | C25，C26–C29 回填 | Phase F 主表 |
| 表 D | 函数调用三分派对照（native thunk / ProcessInternal / RuntimeCallFunction：Func 值、flags、入口、参数打包位置） | C16/C13 | 调用链主线 |
| 表 E | AS EReloadRequirement 触发条件（改动 → Soft/Suggested/Required，含 PIE 降级） | C29（现象版先在 C5 积累） | 日常高频 |
| 表 F | C++ UFUNCTION → AS 命名规则（前缀剥离/属性同名回退/库 namespace 剥离） | C13（现象版先在 C4 积累） | 绑定排障 |
| 表 G | FProperty 子类 CastField 速查（扩展现有 SKILL.md 表，补 FEnumProperty→FNumericProperty 等实战子类） | C18 | 反射速查 |
| 表 H | 命名噪音与再映射规则（GUID 后缀/`_GEN_VARIABLE`/`_C`/ProcessPropertyName/静态映射表） | C18/C21 | BP 反射必备 |
| 表 I | 观测抓手速查（日志频道/控制台/命令行/断点位） | C38 | 全程工具 |
| 表 J | dry-run 纪律与退出码判读（A/B/C 分类、3000/3001、CI 日志可见性） | C22 | 管线日课 |
| 表 K（v2 新增） | AS 五级阶梯进入/退出标准总表（§1.4 的可勾选沉淀） | C0 + 各阶梯末 | 进度门禁 |
| 表 L（v2 新增） | L5 修改阶梯「最小安全修改边界 → 验证方式」矩阵（七行） | C31–C37 回填 | 修改安全网 |
| 表 M（v2 新增） | AS 常用宿主/模式 → 真实项目案例索引（Actor/Component/UObject/Subsystem/容器/委托/定时器/Tag/软引用/DT 批处理/测试） | Phase A/B 回填 | 日常速查 |

## 7. 源码追踪矩阵

> 验证状态说明：**「本次已复核」= 大纲落盘前在当前工作区 grep/定位确认**；「勘察材料」= 来自两份上游勘察、未逐一复核，正文化前需再确认；「v2 定向复核」= v2 修订时为新增应用章做的有限定向检索（非全仓扫描）；「文档记载」= 来自仓库内 SKILL/reference 文档的记述；「二手引用」= 来自团队计划文档的引用，正文化前必须复核。行号均可漂移，符号为主锚点。

| 主题 | 层 | 文件 | 符号 / 锚点 | 验证状态 |
|---|---|---|---|---|
| 函数调用分派 | T1 | Engine/Source/Runtime/CoreUObject/Private/UObject/ScriptCore.cpp | `UObject::ProcessEvent` :2083 | 本次已复核 |
| VM opcode 循环 | T1 | 同上 | `DEFINE_FUNCTION(UObject::ProcessInternal)` :1392；`ProcessLocalScriptFunction` :1245 | 本次已复核 |
| 调用入口 | T1 | Engine/Source/Runtime/CoreUObject/Private/UObject/Class.cpp | `UFunction::Invoke` :7595 | 本次已复核 |
| T2 flag 位 | T2 | Engine/Source/Runtime/CoreUObject/Public/UObject/Script.h | `FUNC_RuntimeGenerated` :142 | 本次已复核 |
| T2 类字段/虚函数 | T2 | Engine/Source/Runtime/CoreUObject/Public/UObject/Class.h | `bIsScriptClass`/`ScriptTypePtr`/`RuntimeCall*`（约 :2694/:4026 区域） | 勘察材料 |
| AS 方法指针擦除 | T2 | Engine/Plugins/Angelscript/Source/AngelscriptCode/Public/ClassGenerator/CoreNative.h | ASAutoCaller（约 :25–227） | 勘察材料 |
| UHT AS 发射 | T2 | UHT C# `UhtHeaderCodeGeneratorCppFile.cs` | `GetASFunctionPointers`（约 :2894–3029/:3082–3085） | 勘察材料 |
| Kismet 编译阶段 | T1 | Engine/Source/Editor/KismetCompiler/Private/KismetCompiler.cpp | `CreateFunctionList` :4685 / `CompileClassLayout` :4749 / `CompileFunctions` 约 :4956 | 本次已复核（前两个） |
| BP 编译编排 | T1 | Engine/Source/Editor/Kismet/Private/BlueprintCompilationManager.cpp | `FlushCompilationQueueAndReinstance` :4563 / `CompileSynchronously` :4599 / `ReinstanceBatch` :2781 | 本次已复核 |
| BP Reinstancing | T1+T2 | Engine/Source/Editor/UnrealEd/Private/Kismet2/KismetReinstanceUtilities.cpp | `GenerateFieldMappings` :674 / `ReinstanceObjects` :1006 / `UpdateBytecodeReferences` :1224 / `BatchReplaceInstancesOfClass` :1941/:1974 | 本次已复核（HAZE 补丁行号待复核） |
| Live Coding | T1 | Engine/Source/Developer/Windows/LiveCoding/Private/LiveCodingModule.cpp | `FLiveCodingModule::Compile`（约 :246） | 路径已复核，行号待复核 |
| 旧 HotReload | T1 | Engine/Source/Developer/HotReload/Private/HotReload.cpp | `DoHotReloadFromEditor`（约 :539–556） | 路径已复核，行号待复核 |
| AS 编译编排 | T3 | Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/AngelscriptManager.cpp | `MakeAllScriptRoots` :268 / `InitialCompile` :892 / `CheckForHotReload` :1480 / `CompileModules` :1798 | 本次已复核 |
| AS 类生成 | T3 | Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/ClassGenerator/AngelscriptClassGenerator.cpp | `ShouldFullReload` :2091 / `PerformReload` :2116 / `InitDefaultObjects` :5828 | 本次已复核（:5828 来自勘察，未复核） |
| UE←AS 调用 | T3 | 同目录 ASClass.cpp | `AngelscriptCallFromBPVM`（约 :105） | 路径已复核，行号待复核 |
| AS→BP 交汇点 | T3 | Engine/Plugins/Angelscript/Source/AngelscriptEditor/Private/ClassReloadHelper.cpp | `PerformReinstance` :24 / :187–189 | 本次已复核 |
| Build() 空壳 | T3 | Engine/Plugins/Angelscript/ThirdParty/source/as_module.cpp | `asCModule::Build()`（约 :290） | 勘察材料（ThirdParty/SKILL.md 同述） |
| 反射实战库 | T4 | Main/Plugins/PLPythonPipeline/Source/PLPythonPipeline/Private/PLPythonAutomationFunctionLibrary.cpp | `SetEntityComponentPropertiesFromDataTable` :807 / `SetEditorObjectProperty` :3825 / `GetObjectProperty` :6215 | 本次已复核 |
| 反射实战其余锚点 | T4 | 同上及 Utils/ 兄弟文件 | CopyPropertyValue :136 / ExportPropertyValueForDryRun :277 / CopyPropertiesFromDataTableRow :295 / ExtractCollisionConfigFromAnimMontage :5010 / 容器段 :5130–5210 / JSON 四函数 :4532–4671 / dry-run 计数 :4470–4485 | 勘察材料 |
| 二进制对照组 | T4 | Main/Plugins/PLPythonPipeline/.../Private/UAssetSemantic/PLPropValueDecoder.cpp | FPropertyTag 解码（0 反射命中） | 勘察材料 |
| AS 调用现场 | T4 | Main/Script/Editor/DataTableRowProcessor/DataTableRowProcessor_PLEntityTagMapping.as | PLPythonAutomation:: 调用 as:174/297/449/461/468/476/477 | 勘察材料 |
| **v2 新增：应用章案例锚点** | | | | |
| UPROPERTY 谱系样本 | T4 | Main/Script/Component/ASInteractionComponent.as | `TSoftClassPtr<UGameplayEffect>`/`Transient`/`EditAnywhere+Category` 属性群（文件头部区域） | v2 定向复核 |
| 纯 AS 测试 Action | T4 | Main/Script/Tests/1000_RuntimeTests/PLAutomationSampleCase.as | `UWaitTicksAsAction : UPLAutomationAction`（BlueprintOverride Tick）；头注释「裸构造限制→builder」实录 | v2 定向复核 |
| C++ 基类 + AS 子类模式 | T4 | Main/Script/Gameplay/Entry/ASDamageFlow_*.as | 17 个真实子类（目录枚举）；C++ 基类 `UPLDamageFlowCalculation` | v2 定向复核（目录枚举）+ 文档记载（Main/Script SKILL code-locations） |
| 委托绑定样本 | T4 | Main/Script/Widget/Core/SubsystemWidget.as；Main/Script/Character/ASCharacterPlayer.as | `AddUObject`/`BindUObject` 命中 | v2 定向复核（grep 命中，未逐行读） |
| 定时器样本 | T4 | Main/Script/Actor/ASActorBed.as 等 | `System::SetTimer`/`System::ClearTimer` 命中 | v2 定向复核（grep 命中，未逐行读） |
| GameplayTag 语法糖使用 | T4 | Main/Script/Gameplay/Ability/ASAbility_AimingBase.as 等 | `GameplayTags::` 命中 | v2 定向复核（grep 命中） |
| tag 自动绑定实现 | T3 | Engine/Plugins/Angelscript/Source/AngelscriptCode/Private/Binds/Bind_FGameplayTag.cpp | `GameplayTags::` 全局量注册（:40–59） | 文档记载（Main/Script/Editor SKILL.md Troubleshooting） |
| ScriptTags 定义 | T4 | Main/Script/Tags/**/*.as | `ScriptTags::Define`（单行字面量铁律） | 文档记载（Main/Script SKILL.md） |
| 编辑器菜单/批处理 | T4 | Main/Script/Editor/EditorMenuExtensions.as / EditorMenuExtensions_Temp.as / DataAutomationUtility.as / UseCases/ | `UScriptEditorMenuExtension`、`Temp_CleanAttributeSet` 限流范式、`UPLDataTableTestingUseCase` | 文档记载（Main/Script/Editor SKILL.md） |
| headless 编译验证 | T3 | 命令行 | `-run=AngelscriptAllScriptRoots -as-force-preprocess-editor-code -as-ignore-precompiled-data -unattended -nullrhi` | 文档记载（Main/Script/Editor SKILL.md Troubleshooting） |
| 覆写把关点 | T3 | AngelscriptPreprocessor.cpp / AngelscriptClassGenerator.cpp | 覆写映射 :1426–1452 / 强制校验 :444–507 | **二手引用**（`.team/sunlaibing/plans/runtime-details-as-script-execution-plan.md`），待复核 |
| 网络用例目录 | T4 | Main/Script/Tests/1000_RuntimeTests/Net/ | 目录存在（C10 最小证据） | v2 定向复核（目录枚举） |

## 8. 已知未知项（诚实清单 — 正文化前必须逐条关闭或显著标注）

来自两份勘察材料的未关闭项 + v2 新增项，**在大纲与后续正文中一律不得写成确定事实**：

1. **行号时效**：所有 file:line 基于当前 P4 工作区快照；正文以符号名为主锚点。
2. **PLScriptAsync 不在 head**：Suspend/恢复、await 脱糖实现仅存在于未提交 shelf 119677/117988；C30 只能按其 SKILL 不变量讲，源码锚点待 rebase 后补。
3. **旧 HotReload 真实触发面**：本分支除 IDE 集成遗留外是否还有触发路径，未确认（C27 核心问题③）。
4. **Binds.Cache 写出侧**（commandlet/cook 管线实现）只引用文档锚点（AngelscriptManager.cpp:407/:427），未读实现。
5. **StaticJIT 转译器内部、`FAngelscriptPreprocessor` 宏展开细节、`Bind_BlueprintEvent.cpp` 覆写机制**：只定位到文件，未下钻。
6. **ThirdParty VM 内部**（as_context Suspend、超级指令 201–221 派发表）：只引用 ThirdParty/SKILL.md 记录。
7. **`EExprToken` 定义确切位置与 exec* 全清单**：仅统计到 ScriptCore.cpp 有 101 个 exec 入口，未逐个核对。
8. **WITH_ANGELSCRIPT_HAZE 死代码**：Hazelight 私有网络层（CrumbFunction）在本分支未启用，相关路径（如 AngelscriptClassGenerator.cpp:3387–3399）为死代码，正文需声明跳过。
9. **`CachePureEvaluation` 实现体**（PLPythonAutomationFunctionLibrary.cpp 约 :6396 起）未逐行细读；若收编蓝图图手术专题需补读 :6381–6665。
10. **`InitializeBlueprintComponentProperties` 疑似笔误**：约 :3022 `Property->ContainerPtrToValuePtr<bool>(SourceProperty)` 疑似把 FProperty* 当 container 传入——是 bug 还是有意为之未求证，引用前需与作者确认。
11. **dry-run 的 BuildingBlock 分支**（约 :951–973）只告警不真正比对 StabilityCalculationMethod 属性——已知简化还是疏漏，未求证。
12. **PLPyStructLib 的 UUserDefinedStruct schema 手术**（39 行 cpp）未细读；`FStructureEditorUtils::GetGuidForProperty` 消费侧（PLAnimNotifyAssetActionUtility.cpp:88–96）可作可选扩展块，未列入主大纲。
13. **Python 侧 2 处 PLPythonAutomation 调用**（`entity_property_table_automation_tools.py`、`da2excel.py`）未展开确认具体函数名。
14. **ue-cli 是否有脚本编译/热更命令面**：未验证。
15. **（v2 新增）C10 网络/协程/异步证据不足**：`Tests/1000_RuntimeTests/Net/` 目录存在但未逐案分析其覆盖语义；HAZE 网络层为死代码（第 8 条）；协程实现不在 head（第 2 条）。三者叠加 ⇒ C10 长期挂「可选/未知」，证据补齐前不正文化。
16. **（v2 新增）覆写把关点行号为二手引用**：`AngelscriptPreprocessor.cpp:1426–1452` 与 `AngelscriptClassGenerator.cpp:444–507` 引自团队计划文档，未在当前工作区复核。
17. **（v2 新增）委托/定时器样本未逐行精读**：C3/C7 的 `AddUObject`、`System::SetTimer` 案例为 grep 命中定位，正文化时需打开文件确认用法细节与真实签名。

## 9. 用户 review 清单（v2）

请逐条裁决（√/×/改）：

1. **AS 主线化**：五级阶梯（L1 日常使用 → L2 应用模式 → L3 行为到原理映射 → L4 源码追踪 → L5 扩展与修改）的组织方式是否接受？各级的进入/退出标准（§1.4）是否合理、可勾选？
2. **先浅后深**：应用篇（Phase A/B，C1–C10）全部置于机制与源码篇之前的顺序是否符合预期？C15（Epic 反射底座）作为 Phase C 软依赖、建议并行插读的处理是否可接受？
3. **章节粒度与周期**：40 章 / 约 54–62 课次 / 5–6.5 个月的体量（v1 为 23 章 / 35–40 课次）是否符合「先浅后深、长期吃透」预期？AS 篇幅从 4/23 章提升到约 22/40 章是否达到 review 反馈的要求？
4. **应用章案例真实性**：C1–C10 每章的案例均来自 Main/Script、项目插件或现有 SKILL/reference（第 7 节矩阵新增行，含验证状态标注）——是否抽查确认？哪些章的案例密度还不够？
5. **L5 修改阶梯**：C31–C37 七级划分（AS 案例 → 自动绑定 → 手写 Bind_* → 类生成器 → RuntimeCall 桥 → 编译阶段/VM → 回归测试）的梯度与「最小安全修改边界 + 验证方式」写法是否合适？是否要写答案式附录（当前刻意不写）？
6. **C10 处理**：网络/协程/异步因证据不足挂「可选/未知」（已知未知项 15），是否接受？还是要求本期补做 Net 用例逐案分析？
7. **每章 7 字段模板**（L5 章为 9 字段）是否够用？是否要加「前置自检」「常见误区」字段？
8. **归属层更名 T1–T4**（为避免与阶梯 L1–L5 混淆）是否接受？备选：阶梯改用 S1–S5。
9. **章节顺序（v1 遗留问题重提）**：PLPythonPipeline 精读现位于 Phase E（Epic 底座之后、热更新之前），硬依赖仅 C15+C16 可并行——可否接受？
10. **可选扩展块**是否收编：UUserDefinedStruct schema 手术（PLPyStructLib）、蓝图图手术专题（CachePureEvaluation 等 :6381–6665）、StaticJIT 内部、Preprocessor 宏展开。
11. **PLScriptAsync** 处理：shelf 期间按 SKILL 不变量讲 + 显著标注，还是整段推迟到 rebase 之后？
12. **验收形式**：阶梯退出标准（表 K）+ 口述 + 笔记 + 对照表回填，当前为混合制——是否需要统一为可勾选的验收记录表？
13. **语言**：当前为中文主体 + 英文符号；是否需要双语或纯英文版？
14. **文件归属**：确认放本路径（`.claude/skills/ue-blueprint-reflection/references/source-study-outline.md`，与 property-access/container-helpers 并列）——备选 `ClaudeReadmes/WorkBook/` 已否（语义为单次事件型笔记）。
15. **后续动作授权**：见下节，是否一并批准、还是等正文首批章节完成后再做？

## 10. 大纲批准后的后续动作（当前一律未执行）

1. `p4 add` 本文件（新建 CL，描述纯 ASCII）。
2. 在 `.claude/skills/ue-blueprint-reflection/SKILL.md` 的「相关文件」节加一行索引指向本文件。
3. 跑 `cmd.exe /c skill_index_gen.bat` 重建索引（脚本自带 p4 edit + revert -a）。
4. （可选）在 `Main/Plugins/PLPythonPipeline/references/asset-query-extension.md` 或其 SKILL.md 知识索引加一条交叉引用——命中 Tier-2 ask 拦截，需用户当场批准。
5. 正文写作按本大纲逐章进行（Phase A 优先），每章完成后回到第 3 节勾选。

## 附录 A. 材料来源

- 勘察 A（PLPythonPipeline 反射实战）：`C:\Users\admin\AppData\Local\Temp\recon_A_plpythonpipeline_reflection_material.md`（临时文件，事实性内容已全部并入本大纲第 2/6/7/8 节）
- 勘察 B（AS/BP VM/热重载大纲）：`C:\Users\admin\AppData\Local\Temp\task_7be7162d98b9_as_bp_vm_outline.md`（临时文件，章节骨架与四层模型已并入重组）
- v2 新增案例的定向复核：`Main/Script/` 目录枚举与定点 grep（Component/ASInteractionComponent.as、Tests/1000_RuntimeTests/PLAutomationSampleCase.as、Gameplay/Entry/ASDamageFlow_*.as、Widget/Core/SubsystemWidget.as、Actor/ASActorBed.as、Tests/1000_RuntimeTests/Net/ 等，详见第 7 节矩阵「v2 定向复核」行）
- 核对基准：`.claude/skills/ue-blueprint-reflection/SKILL.md`、`Main/Plugins/PLPythonPipeline/SKILL.md`、`Engine/Plugins/Angelscript/SKILL.md`、`Engine/Plugins/Angelscript/ThirdParty/SKILL.md`、`Main/Script/SKILL.md`、`Main/Script/Editor/SKILL.md`、CLAUDE.md/AGENTS.md
- 落盘前抽查复核：见第 7 节「验证状态」列

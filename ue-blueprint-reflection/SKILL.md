---
name: ue-blueprint-reflection
title: UE Blueprint/C++ Reflection API 参考
description: UE C++ 反射读写 Blueprint 属性参考。涉及 FScriptMapHelper、FObjectProperty、FStructProperty、TMap/TArray/TSet 或容器属性遍历时使用。
tags: [C++, Blueprint, Reflection, UE5, Editor-Tools, Data-Driven]
---

# UE Blueprint/C++ Reflection API 参考

> Layer: Tier 3 (Workflow Reference)

## 核心原则

Blueprint 类的属性名在反射系统里存的是**显示名（Display Name）**，不是 C++ 字段名。Blueprint 结构体字段名通常带数字或 GUID 后缀（如 `DataAsset_5_A1B2C3D4`）。永远不要用精确名匹配 Blueprint 属性，用前缀匹配或迭代器。

---

## 属性查找

### 精确查找（仅用于 C++ 原生类）

```cpp
FProperty* Prop = SomeClass->FindPropertyByName(TEXT("MyField"));
```

### Blueprint 类属性 — 用前缀匹配

```cpp
FObjectProperty* DataAssetProp = nullptr;
for (TFieldIterator<FProperty> It(SomeStruct); It; ++It)
{
    if (It->GetName().StartsWith(TEXT("DataAsset")))
    {
        DataAssetProp = CastField<FObjectProperty>(*It);
        break;
    }
}
```

### 打印所有属性名（调试用）

```cpp
for (TFieldIterator<FProperty> It(SomeClass); It; ++It)
{
    UE_LOG(LogTemp, Warning, TEXT("Prop: '%s'"), *It->GetName());
}
```

---

## 属性类型转换

| 目标类型 | API |
|---------|-----|
| 对象引用 | `CastField<FObjectProperty>(Prop)` |
| 结构体 | `CastField<FStructProperty>(Prop)` |
| TMap | `CastField<FMapProperty>(Prop)` |
| TArray | `CastField<FArrayProperty>(Prop)` |
| bool | `CastField<FBoolProperty>(Prop)` |
| int32 | `CastField<FIntProperty>(Prop)` |
| FString | `CastField<FStrProperty>(Prop)` |
| FName | `CastField<FNameProperty>(Prop)` |
| FGameplayTag | `CastField<FStructProperty>(Prop)` → 验证 `Struct == FGameplayTag::StaticStruct()` |

> `GetValueProperty()` / `GetKeyProperty()` 返回 `const FProperty*`，声明时加 `const`，否则编译报"丢失限定符"。

```cpp
// 正确
const FStructProperty* ValueStructProp = CastField<FStructProperty>(MapProp->GetValueProperty());
const FStructProperty* KeyStructProp   = CastField<FStructProperty>(MapProp->GetKeyProperty());
```

---

## 读写对象属性值 / 结构体字段访问

`PLPythonAutomation::GetObjectProperty` 快捷封装、底层 `*_InContainer` API、结构体内字段前缀匹配访问：

> 详细参考：[property-access](references/property-access.md)

## TMap / TArray 运行时操作

`FScriptMapHelper` / `FScriptArrayHelper` 遍历与写回、完整实战案例（`ExtractCollisionConfigFromAnimMontage` 处理 `ANS_PLCollisionByTags_C`）：

> 详细参考：[container-helpers](references/container-helpers.md)

---

## 常见陷阱

| 陷阱 | 原因 | 解决 |
|------|------|------|
| `FindPropertyByName` 返回 null | Blueprint 属性名带后缀 | 用 `TFieldIterator` + `StartsWith` |
| `CastField` 返回 null | 属性类型不匹配 | 先打印 `Prop->GetClass()->GetName()` 确认类型 |
| `GetValueProperty()` 编译报"丢失限定符" | 返回 `const FProperty*` 但声明为非 const | 加 `const` |
| 写回 TMap 后数据丢失 | 直接修改 copy 而非原始内存 | 用 `GetValuePtr` 拿到原始指针再写 |
| Blueprint 子类 Cast 失败 | `NotifyStateClass.Get()` 返回的是 CDO | 确认用 `.Get()` 而非 `->GetClass()` |

---

## 相关文件

- `Main/Plugins/PLPythonPipeline/Source/PLPythonPipeline/Public/PLPythonAutomationFunctionLibrary.h` — `GetObjectProperty`、`SetEditorObjectProperty` 等反射工具函数声明（首查此处）
- [PLPythonPipeline SKILL.md](../../../Main/Plugins/PLPythonPipeline/SKILL.md) — 可调用的反射工具函数总览（`GetObjectProperty` 等）

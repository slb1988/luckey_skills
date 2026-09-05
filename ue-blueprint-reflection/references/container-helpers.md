# 容器属性运行时操作（FScript*Helper）与实战案例

## TMap 运行时操作（FScriptMapHelper）

```cpp
FMapProperty* MapProp = CastField<FMapProperty>(
    SomeClass->FindPropertyByName(TEXT("MyMap")));

FScriptMapHelper MapHelper(MapProp, MapProp->ContainerPtrToValuePtr<void>(OwnerPtr));

for (int32 i = 0; i < MapHelper.Num(); ++i)
{
    if (!MapHelper.IsValidIndex(i)) continue;

    void* KeyPtr   = MapHelper.GetKeyPtr(i);
    void* ValuePtr = MapHelper.GetValuePtr(i);

    // 读 Key（FGameplayTag 示例）
    const FStructProperty* KeyStructProp = CastField<FStructProperty>(MapProp->GetKeyProperty());
    const FGameplayTag* Tag = KeyStructProp->ContainerPtrToValuePtr<FGameplayTag>(KeyPtr);

    // 读/写 Value 内的字段
    const FStructProperty* ValStructProp = CastField<FStructProperty>(MapProp->GetValueProperty());
    FObjectProperty* DataAssetProp = /* 前缀匹配查找 */;

    UObject* Existing = DataAssetProp->GetObjectPropertyValue(
        DataAssetProp->ContainerPtrToValuePtr<void>(ValuePtr));

    DataAssetProp->SetObjectPropertyValue(
        DataAssetProp->ContainerPtrToValuePtr<void>(ValuePtr), NewObj);
}
```

---

## TArray 运行时操作（FScriptArrayHelper）

```cpp
FArrayProperty* ArrProp = CastField<FArrayProperty>(
    SomeClass->FindPropertyByName(TEXT("MyArray")));

FScriptArrayHelper ArrHelper(ArrProp, ArrProp->ContainerPtrToValuePtr<void>(OwnerPtr));

for (int32 i = 0; i < ArrHelper.Num(); ++i)
{
    void* ElemPtr = ArrHelper.GetRawPtr(i);
    // 用 ArrProp->Inner 访问元素属性
    FObjectProperty* ElemObjProp = CastField<FObjectProperty>(ArrProp->Inner);
    UObject* Obj = ElemObjProp->GetObjectPropertyValue(ElemObjProp->ContainerPtrToValuePtr<void>(ElemPtr));
}
```

---

## 实战案例：遍历 Blueprint TMap 并写回 DataAsset

本项目中 `ExtractCollisionConfigFromAnimMontage` 处理 `ANS_PLCollisionByTags_C` 的完整流程：

```cpp
// 1. 找 TMap 属性
FMapProperty* MapProp = CastField<FMapProperty>(
    NotifyClass->FindPropertyByName(TEXT("TagCollisionPackages")));

// 2. 获取 Value 结构体类型
const FStructProperty* ValueStructProp = CastField<FStructProperty>(MapProp->GetValueProperty());

// 3. 在 Value 结构体内找 DataAsset 字段（前缀匹配）
FObjectProperty* DataAssetProp = nullptr;
for (TFieldIterator<FProperty> It(ValueStructProp->Struct); It; ++It)
{
    if (It->GetName().StartsWith(TEXT("DataAsset")))
    {
        DataAssetProp = CastField<FObjectProperty>(*It);
        break;
    }
}

// 4. 获取 Key 类型（C++ 原生结构体可直接用）
const FStructProperty* KeyStructProp = CastField<FStructProperty>(MapProp->GetKeyProperty());

// 5. 遍历 Map
FScriptMapHelper MapHelper(MapProp, MapProp->ContainerPtrToValuePtr<void>(NotifyState));
for (int32 i = 0; i < MapHelper.Num(); ++i)
{
    if (!MapHelper.IsValidIndex(i)) continue;

    void* ValuePtr = MapHelper.GetValuePtr(i);
    const FGameplayTag* Tag = KeyStructProp->ContainerPtrToValuePtr<FGameplayTag>(
        MapHelper.GetKeyPtr(i));

    // 6. 读现有值
    UObject* Existing = DataAssetProp->GetObjectPropertyValue(
        DataAssetProp->ContainerPtrToValuePtr<void>(ValuePtr));
    if (Existing) continue; // 已有则跳过

    // 7. 写回新值
    DataAssetProp->SetObjectPropertyValue(
        DataAssetProp->ContainerPtrToValuePtr<void>(ValuePtr), NewAsset);
}
```

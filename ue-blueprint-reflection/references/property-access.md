# 属性值读写与结构体字段访问（详细版）

## 读写对象属性值

### 快捷方式：GetObjectProperty（推荐用于 AS 场景）

`PLPythonAutomationFunctionLibrary.h` 中已有通用封装，AS 可直接调用：

```angelscript
// 读取任意 FObjectProperty（包括 WITH_EDITORONLY_DATA 字段）
UObject Result = PLPythonAutomation::GetObjectProperty(TargetObject, n"PropertyName");
bool bExists = Result != nullptr;
```

C++ 实现核心（`FindFProperty` + `GetObjectPropertyValue_InContainer`）：

```cpp
FObjectPropertyBase* Prop = FindFProperty<FObjectPropertyBase>(TargetObject->GetClass(), PropertyName);
return Prop ? Prop->GetObjectPropertyValue_InContainer(TargetObject) : nullptr;
```

### 底层 API（需要自己操作原始指针时）

```cpp
// 读
UObject* Obj = ObjectProp->GetObjectPropertyValue_InContainer(OwnerPtr);
// 或（已有 ValuePtr）
UObject* Obj = ObjectProp->GetObjectPropertyValue(ObjectProp->ContainerPtrToValuePtr<void>(ValuePtr));

// 写
ObjectProp->SetObjectPropertyValue_InContainer(OwnerPtr, NewObj);
// 或（已有 ValuePtr）
ObjectProp->SetObjectPropertyValue(ObjectProp->ContainerPtrToValuePtr<void>(ValuePtr), NewObj);
```

---

## 结构体内字段访问

```cpp
FStructProperty* StructProp = CastField<FStructProperty>(
    SomeClass->FindPropertyByName(TEXT("MyStruct")));

void* StructPtr = StructProp->ContainerPtrToValuePtr<void>(OwnerPtr);

// 在结构体内查找字段（Blueprint 结构体用前缀匹配）
FObjectProperty* InnerProp = nullptr;
for (TFieldIterator<FProperty> It(StructProp->Struct); It; ++It)
{
    if (It->GetName().StartsWith(TEXT("DataAsset")))
    {
        InnerProp = CastField<FObjectProperty>(*It);
        break;
    }
}

UObject* Val = InnerProp->GetObjectPropertyValue(
    InnerProp->ContainerPtrToValuePtr<void>(StructPtr));
```

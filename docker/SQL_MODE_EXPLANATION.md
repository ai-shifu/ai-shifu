# MySQL sql_mode 配置详解

## 问题根源

错误 `Invalid default value for 'updated'` 是由 **`NO_ZERO_DATE`** 模式导致的。

## MySQL 8.0 默认 sql_mode

MySQL 8.0 的默认 `sql_mode` 通常包含：
```
ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
```

## 关键点：移除 NO_ZERO_DATE

我们提供的配置：
```sql
SET GLOBAL sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';
```

**注意对比**：
- ❌ **移除了**：`NO_ZERO_DATE` 和 `NO_ZERO_IN_DATE`
- ✅ **保留了**：`STRICT_TRANS_TABLES`（严格模式仍然开启）

## 各模式说明

| 模式 | 作用 | 是否保留 | 原因 |
|------|------|---------|------|
| `ONLY_FULL_GROUP_BY` | 要求 GROUP BY 包含所有非聚合列 | ✅ 保留 | 数据完整性 |
| `STRICT_TRANS_TABLES` | 严格模式，拒绝无效数据 | ✅ 保留 | 数据完整性 |
| `NO_ZERO_DATE` | **禁止使用 '0000-00-00' 作为日期，要求 TIMESTAMP 必须有默认值** | ❌ **移除** | **这是导致错误的根源** |
| `NO_ZERO_IN_DATE` | 禁止使用 '0000-00-00' 格式的日期 | ❌ 移除 | 与 NO_ZERO_DATE 相关 |
| `ERROR_FOR_DIVISION_BY_ZERO` | 除零错误 | ✅ 保留 | 数据完整性 |
| `NO_ENGINE_SUBSTITUTION` | 禁止自动替换存储引擎 | ✅ 保留 | 配置完整性 |

## 解决方案总结

**不是"添加了某个模式"，而是"移除了 `NO_ZERO_DATE` 模式"**

### 最小化修改方案

如果你只想移除问题模式，可以这样：

```sql
-- 获取当前模式
SELECT @@GLOBAL.sql_mode;

-- 移除 NO_ZERO_DATE 和 NO_ZERO_IN_DATE
SET GLOBAL sql_mode = REPLACE(REPLACE(@@GLOBAL.sql_mode, 'NO_ZERO_DATE,', ''), 'NO_ZERO_IN_DATE,', '');
SET GLOBAL sql_mode = REPLACE(REPLACE(@@GLOBAL.sql_mode, ',NO_ZERO_DATE', ''), ',NO_ZERO_IN_DATE', '');
```

### 完整配置方案（推荐）

使用我们提供的完整配置，确保所有模式都是明确的：

```sql
SET GLOBAL sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';
```

## 验证

执行后检查：
```sql
SELECT @@GLOBAL.sql_mode;
```

确认输出中**不包含** `NO_ZERO_DATE` 和 `NO_ZERO_IN_DATE`。

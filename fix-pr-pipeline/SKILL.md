---
name: fix-pr-pipeline
description: 修复 PR CI/CD 流水线失败的系统化方法。当 PR 流水线（TeamCity、GitHub Actions）出现编译错误、UT 失败、格式检查失败等问题时使用。涵盖常见错误模式、诊断流程和本地验证清单。
---

# 修复 PR 流水线问题

## 核心原则

**提交前必须本地验证，绝不盲推代码到远程。**

每次修复后，必须按以下顺序完成本地验证：
1. clang-format 检查（使用 CI 同版本）
2. **Clang 编译通过**（默认 ASAN 构建）
3. **GCC 编译通过**（Performance 流水线使用 GCC）
4. 运行相关 UT 全部通过
5. 确认无遗漏后再 push

## 诊断流程

### Step 1: 获取失败信息

```bash
# 使用 teamcity skill 诊断
bash ~/.claude/skills/teamcity/teamcity.sh diagnose <build_id>

# 查看具体失败的测试
bash ~/.claude/skills/teamcity/teamcity.sh tests <build_id> FAILURE

# GitHub Actions 日志
gh run view <run_id> --log-failed
```

### Step 2: 分类错误类型

| 类型 | 识别方式 | 优先级 |
|------|----------|--------|
| 编译错误 | `error:` in build log | P0 - 最高 |
| UT SEGV/Crash | `SEGV`, `Signal 11`, `AddressSanitizer` | P0 - 最高 |
| UT 测试失败 | `FAILED` in test output | P1 |
| Clang Formatter | GitHub Actions "Clang Formatter" 失败 | P1 |
| FE Checkstyle | `checkstyle:check` 失败 | P1 |
| Regression Test | P0/cloud_p0 失败 | P1 |
| 非代码问题 | Performance clean step, macOS, coverage | P2 - 可忽略 |

### Step 3: 逐一修复

按优先级从高到低修复。每修复一个问题后立即本地验证。

## 常见错误模式与修复方案

### 1. GCC vs Clang 编译差异（-Werror=overloaded-virtual）

**问题**: 本地 Clang 编译通过，CI 的 GCC Performance 流水线报错。

**典型错误**: `-Werror=overloaded-virtual`
```
error: 'virtual TokenStream* Field::tokenStreamValue()' was hidden [-Werror=overloaded-virtual=]
```

**修复**: 在派生类中添加 `using Base::method_name;` 声明
```cpp
class FieldForMerge : public Field {
public:
    using Field::stringValue;      // 引入基类的非 const 版本
    using Field::readerValue;
    using Field::tokenStreamValue;

    const TCHAR* stringValue() const;         // 派生类的 const 版本
    Reader* readerValue() const;
    TokenStream* tokenStreamValue() const;
};
```

**⚠️ 关键教训**:
- Clang 对 `-Woverloaded-virtual` 检查较宽松，GCC (尤其 14+) 更严格
- GCC 14+ 中 `-Wall` 包含了 `-Woverloaded-virtual=1`
- **不能只靠 `#pragma` 压制！** 如果同一个基类头文件通过不同的 include 链被引入，pragma 只能包住其中一条链，另一条链引入时没有 pragma 保护，GCC 仍然报错
- **正确做法：在源头（派生类定义处）修复**，而不是在消费者侧加 pragma

### 2. GCC vs Clang 编译差异（-Werror=reorder）

**问题**: 构造函数初始化列表顺序与成员变量声明顺序不一致。

**典型错误**:
```
error: 'freqStream_' will be initialized after 'maxDoc' [-Werror=reorder]
```

**修复**: 调整初始化列表顺序与成员变量声明顺序一致。

### 3. GCC vs Clang 编译差异（-Werror=inaccessible-base）

**问题**: 菱形继承导致基类不可访问。

**修复方案对比**:
| 方案 | 优点 | 缺点 |
|------|------|------|
| `virtual` 继承 | 语义正确 | `static_cast` 从虚基类向下转型会编译失败 |
| `#pragma GCC diagnostic ignored` | 简单，不改运行时行为 | 只是压制警告 |

**⚠️ 关键教训**: 不要盲目使用 `virtual` 继承修复菱形继承！如果代码中有 `static_cast` 从基类向派生类的转型，`virtual` 继承会导致编译失败：
```
error: cannot convert from pointer to base class 'TermFreqVector'
       to pointer to derived class 'SegmentTermVector' because the base is virtual
```
此时应使用 `#pragma GCC diagnostic` 压制。

### 4. pragma 保护的局限性（include 链问题）

**问题**: 用 `#pragma diagnostic` 包裹第三方库的 include，但该头文件已通过其他路径被 include，pragma 不生效。

**典型场景**:
```
doc_set_collector.cpp
  → doc_set_collector.h → ... → exec_env.h → inverted_index_writer.h
    → CLucene.h → Document.h → Field.h  (无 pragma，Field.h 已缓存)
  → multi_segment_util.h  (#pragma push)
    → _MultiSegmentReader.h → _FieldsReader.h (FieldForMerge 隐藏 Field 方法)
                               (#pragma pop)
```
`_FieldsReader.h` 在 pragma 范围内，但 `Field.h` 早已通过另一条链被 include（无 pragma），GCC 将 warning 关联到 `Field.h` 的声明位置。

**⚠️ 核心规则**: **pragma 保护只在"该头文件首次被 include"时有效**。如果头文件通过多条 include 链引入，必须在源头修复问题，而非在消费者侧加 pragma。

### 5. 接口变更导致调用点遗漏

**问题**: 修改了函数签名（增加参数），但部分调用点未更新。

**修复方法**:
```bash
# 搜索所有调用点
grep -rn "function_name(" be/src/ be/test/ --include="*.cpp" --include="*.h"
```

**教训**: 修改函数签名后，必须用 grep 搜索所有调用点。编译器有时会因为前面的 `-Werror` 而掩盖后续的编译错误。

### 6. `std::move` 导致成员变量被清空

**问题**: 在可能多次调用的方法中对成员变量使用 `std::move`。

**修复**: 对成员变量使用拷贝，不要 move
```cpp
// 错误：_field 被移走，第二次调用时为空
auto weight = std::make_shared<RegexpWeight>(_context, std::move(_field), ...);
// 正确：拷贝 _field
auto weight = std::make_shared<RegexpWeight>(_context, _field, ...);
```

### 7. UT 环境中指针为 nullptr

**问题**: 生产代码中的指针在 UT 环境下为 nullptr，导致 SEGV。

**修复**: 添加 nullptr 检查
```cpp
if (_context->runtime_state) {
    _max_expansions = _context->runtime_state->query_options().inverted_index_max_expansions;
}
// _max_expansions 已有默认值 0
```

**教训**: `runtime_state`、`query_ctx` 等在 UT 环境中经常为空。

### 8. 第三方库接口变更（CLucene submodule）

**问题**: 更新了 CLucene submodule，新增/重命名了虚函数，但 UT 中的 mock 类未同步更新。

**修复**: Mock 类需要同时实现新旧接口
```cpp
class MockTermDocs : public lucene::index::TermDocs {
    bool _fillDocRange(DocRange* docRange) { /* ... */ }
    bool readRange(DocRange* docRange) override { return _fillDocRange(docRange); }
    bool readBlock(DocRange* docRange) override { return _fillDocRange(docRange); }
};
```

### 9. 算法逻辑错误（比较器方向）

**问题**: 使用自定义比较器时，`min_element` / `max_element` 的语义与预期相反。

```cpp
struct ScoredDocByScoreDesc {
    bool operator()(const ScoredDoc& a, const ScoredDoc& b) const {
        return a.score > b.score;  // 降序：高分 = "小"
    }
};
// 错误：min_element + 降序比较器 → 返回最高分
auto it = std::ranges::min_element(_buffer, ScoredDocByScoreDesc {});
// 正确：max_element + 降序比较器 → 返回最低分（作为阈值）
auto it = std::ranges::max_element(_buffer, ScoredDocByScoreDesc {});
```

### 10. Clang-Format 版本不匹配

**CI 使用版本**: clang-format **16**

```bash
pip3 install clang-format==16.0.6
CF16=$(python3 -c "import clang_format; print(clang_format.__file__.replace('__init__.py', 'data/bin/clang-format'))")
$CF16 -i --style=file <file>
```

### 11. Regression Test 错误信息不匹配

**问题**: FE 修改了错误信息，但 regression test 中的 expected 字符串未更新。

```bash
grep -rn "旧错误信息" regression-test/ --include="*.groovy"
```

### 12. git update-index --cacheinfo hash 错误（Worktree submodule）

**问题**: Worktree 中 `contrib/*` 是符号链接，无法用正常 git submodule 命令操作，需要用 `git update-index --cacheinfo` 手动更新 submodule 引用。但如果 40 位完整 hash 填错（如自己拼凑而非从 `git rev-parse` 获取），CI 会报找不到 commit。

**⚠️ 关键规则**:
```bash
# 永远从 git rev-parse 获取完整 hash，不要手动拼写！
FULL_HASH=$(cd /path/to/submodule && git rev-parse HEAD)
git update-index --cacheinfo 160000,${FULL_HASH},contrib/clucene

# 验证
git diff --cached --raw --no-abbrev | grep clucene
# 确认 40 位 hash 完全正确
```

**教训**: 短 hash（如 `c51b5cc9adc`）可能正确，但完整 hash 拼错一个字符就会导致 CI 找不到 commit。`git diff --cached` 的默认缩写显示可能掩盖错误。**必须用 `--no-abbrev` 验证完整 hash**。

### 13. doris-thirdparty 修复流程

**完整流程**:
```bash
# 1. 在 doris-thirdparty 仓库修复
cd /path/to/doris-thirdparty
git checkout -b fix-xxx origin/clucene
# ... 修改代码 ...
git commit && git push jk fix-xxx

# 2. 提 PR 到 apache/doris-thirdparty (base: clucene)
gh pr create --repo apache/doris-thirdparty --base clucene \
  --head <your-fork-owner>:fix-xxx --title "..." --body "..."

# 3. 等 PR 合入后，获取正确的完整 hash
cd /path/to/doris/contrib/clucene
git fetch origin clucene
git checkout origin/clucene
FULL_HASH=$(git rev-parse HEAD)

# 4. 在 Doris worktree 中更新 submodule
git update-index --cacheinfo 160000,${FULL_HASH},contrib/clucene

# 5. 验证完整 hash 正确
git diff --cached --raw --no-abbrev | grep clucene

# 6. 提交并推送
git commit -m "[fix](clucene) Update clucene submodule ..."
git push
```

**⚠️ 注意**: 如果需要在 Doris 本地验证 CLucene 修改效果（PR 还没合入前），可以直接修改 `contrib/clucene/src/...` 中的文件进行编译测试，但提交 submodule 引用时必须指向远程已合入的 commit。

## 本地验证清单

### ⚡ 双编译器验证（最重要！）

```bash
# 1. Clang 编译（默认 ASAN）
BUILD_TYPE_UT=DEBUG ./build.sh --be -j 100

# 2. GCC 编译（Performance 流水线）
BUILD_TYPE=RELEASE DORIS_TOOLCHAIN=gcc ./build.sh --be -j 100
# 或增量验证特定文件：
cd be/build_Release && ninja -j 100 <target.cpp.o>
```

**⚠️ 必须两个都通过才能推送！** Clang 通过 ≠ GCC 通过。

### BE 代码修改

```bash
# 1. Clang-Format 检查（使用 v16）
CF16=<path-to-clang-format-16>
for f in $(git diff --name-only <base>..HEAD -- 'be/src/*.h' 'be/src/*.cpp' 'be/test/*.h' 'be/test/*.cpp'); do
    diff <($CF16 --style=file "$f") "$f" > /dev/null 2>&1 || echo "NEEDS FORMAT: $f"
done

# 2. 编译 BE UT
BUILD_TYPE_UT=DEBUG ./run-be-ut.sh -j 100

# 3. 运行相关 UT
BUILD_TYPE_UT=DEBUG ./run-be-ut.sh --run --filter="*相关TestSuite*" -j 100

# 4. 确认全部通过
# 输出应显示: [PASSED] N tests. 且无 FAILED
```

### FE 代码修改

```bash
# 1. Checkstyle 检查
cd fe && mvn checkstyle:check -pl fe-core -Dcheckstyle.skip=false

# 2. Import 排序检查
# Java imports 必须严格按字母顺序排列

# 3. FE UT（如有修改）
cd fe && mvn test -pl fe-core
```

### Regression Test 修改

```bash
# 使用 order_qt 或手动 order by
# 使用 test{sql, exception} 模式处理预期错误
# 不要在测试结束时 drop 表
```

## 工作流模板

```
1. 诊断 CI 失败
   └─ teamcity diagnose / gh run view --log-failed

2. 分类并排序错误
   └─ 编译 > SEGV > UT失败 > 格式 > Regression

3. 逐一修复
   ├─ 读取相关源码和接口定义
   ├─ grep 搜索所有受影响的调用点
   └─ 修复代码

4. 本地验证（每次修复后）
   ├─ clang-format-16 检查
   ├─ Clang 编译通过
   ├─ GCC 编译通过（⚠️ 不要省略！）
   └─ UT 全部通过

5. 提交并推送
   ├─ git add <specific-files>  # 不要 git add -A
   ├─ git commit
   ├─ git push
   └─ gh pr comment <PR> --body "run buildall"

6. 监控 CI 结果
   └─ teamcity branch-builds <branch>
```

## 已知的"陷阱"清单

| 陷阱 | 说明 | 防范措施 |
|------|------|----------|
| **pragma 保护失效** | 头文件通过多条 include 链引入时，pragma 只能覆盖其中一条 | 在源头（派生类定义处）修复，不要在消费者侧加 pragma |
| **Clang 通过 ≠ GCC 通过** | GCC 有更严格的 `-Woverloaded-virtual`、`-Wreorder` 等检查 | 双编译器验证：Clang ASAN + GCC Release |
| **virtual 继承破坏 static_cast** | `virtual` 继承修复菱形继承后，`static_cast` 向下转型编译失败 | 用 `#pragma` 压制，或用 `dynamic_cast` |
| **submodule hash 拼错** | `git update-index --cacheinfo` 中 40 位 hash 手动输入出错 | 必须用 `git rev-parse HEAD` 获取，用 `--no-abbrev` 验证 |
| 错误被掩盖 | GCC `-Werror` 导致第一个错误后停止编译，掩盖后续错误 | 修复第一个错误后重新编译 |
| Worktree submodule 符号链接 | worktree 中 `contrib/*` 是符号链接，`git submodule` 命令失败 | 使用 `git update-index --cacheinfo` 手动更新 |
| UT binary 找不到 libjvm.so | 直接运行 `doris_be_test` 会失败 | 必须通过 `run-be-ut.sh` 运行 |
| clang-format 版本差异 | v16 vs v20 格式化结果不同 | `pip3 install clang-format==16.0.6` |
| Mock 类缺少纯虚函数 | 新增纯虚方法后 mock 无法实例化 | 更新 submodule 后搜索所有 mock 类 |
| `std::move` 成员变量 | 多次调用的方法中 move 了成员 | 对成员变量只用拷贝 |
| 降序比较器 + min/max | 语义反转容易出错 | 用具体例子手动验证 |

## GCC 本地编译速查

```bash
# 首次 GCC 编译（创建 custom_env.sh 或设置环境变量）
BUILD_TYPE=RELEASE DORIS_TOOLCHAIN=gcc ./build.sh --be -j 100

# 增量验证（只编译特定失败的文件，非常快）
cd be/build_Release
ninja -j 100 src/storage/CMakeFiles/Storage.dir/path/to/failed_file.cpp.o

# 查看 GCC 编译所有错误
grep "FAILED:" /tmp/gcc_build_output.log
grep "error:" /tmp/gcc_build_output.log | grep -v "^In file"
```

## 触发条件

当遇到以下情况时，应参考此 skill：
- CI/CD 流水线失败需要修复
- PR 提交后出现编译错误、UT 失败
- Clang Formatter 或 FE Checkstyle 检查失败
- 需要在 push 前进行本地验证
- 更新了第三方 submodule 导致接口不兼容
- **Performance 流水线（GCC）编译失败**
- **Worktree 中操作 submodule 引用**

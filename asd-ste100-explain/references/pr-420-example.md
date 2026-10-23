# Worked example: PR #420

This example illustrates the explanation method using the source snapshot
inspected on 2026-10-23. The source PR is
[apache/doris-thirdparty#420](https://github.com/apache/doris-thirdparty/pull/420).
The inspected base was `08d45e541fef1e48dc4ab00d2d5fde9569b49ee3`; the
inspected head was `f2864e07f08583b5cc948e87e82294fd0fd5de16`.

The numerical reproduction and test results below were reported by the PR
author. They are not tests executed by this skill. Status and pending-work
statements describe that source snapshot. Recheck live sources before using
those statements as current facts.

## Transferable decisions

- Define document, token, and frequency before explaining the counters.
- Follow the value from compaction output into the consumer's scoring formula.
- Use one minimal dataset to show both incorrect arithmetic and changed ranking.
- Explain per-destination accounting separately from filtering deleted documents.
- Separate the library guard from the application's raw-data rebuild path.
- State the scope of reported tests and pending integration validation.

Reuse those decisions, not the particular glossary, dataset, or section count.
The main skill's source-verification steps still apply to every new request.

## Chinese explanation

**PR #420 修复了倒排索引合并后的 BM25 评分统计错误。** 旧代码保留了已删除文档的词元数。合并后的索引与重新建立的索引，可能因此给相同文档打出不同分数，甚至交换排名。[PR 说明](https://github.com/apache/doris-thirdparty/pull/420)

下面用固定术语说明问题：

| 术语 | 本文含义 |
|---|---|
| 文档 | 一行数据的 `body` 字段 |
| 词元 | 分词器输出的单位，重复出现也计数 |
| 词频 | 一个词元在一篇文档中出现的次数 |
| 索引合并 | 把源索引中的保留文档写入目标索引 |

**错误来自词元总数与保留文档不一致。** 索引合并通过行号映射跳过已删除文档。但旧代码直接累加源索引的词元总数，没有扣除已删除文档的词元。旧代码随后把全部总数写入第一个目标索引，其余目标索引写零。因此，删除文档和输出多个目标索引都可能造成统计错误。[旧代码](https://github.com/apache/doris-thirdparty/blob/08d45e541fef1e48dc4ab00d2d5fde9569b49ee3/src/core/CLucene/index/IndexWriter.cpp#L1330)

**错误的平均文档长度会改变 BM25 分数。** BM25 是一种搜索评分算法。BM25 用文档长度与平均文档长度的比值计算分数。Doris 按“词元总数 ÷ 文档数”计算平均文档长度。[平均长度计算代码](https://github.com/apache/doris/blob/c7ffbda38772c84c41139bab930a2e704866f50e/be/src/storage/index/inverted/reader/collection_statistics.cpp#L463)

PR 作者在 Doris 4.1.5 上给出了以下复现。作者使用单桶 `UNIQUE KEY` 表和英文倒排索引。作者关闭自动合并，再触发全量合并。表中长度均为词元数。

| 文档 | 内容 | 长度 | 合并后状态 |
|---|---|---:|---|
| A | `alpha` | 1 | 保留 |
| B | 2 个 `alpha`，加 14 个 `omega` | 16 | 保留 |
| C | 240 个 `alpha`，加 16 个 `omega` | 256 | 带删除标记，合并时移除 |

目标索引应包含 17 个词元，即 1＋16。旧代码却写入 273，即 1＋16＋256。目标索引只剩 2 篇文档，所以错误的平均长度是 136.5，正确值是 8.5。

作者执行 `SEARCH('body:alpha')`，按 `score()` 降序排列：

| 索引生成方式 | A 的分数 | B 的分数 | 排名 |
|---|---:|---:|---|
| 旧代码直接合并 | 0.3069872 | 0.33349273 | B、A |
| 只用保留文档重新建立索引 | 0.28530657 | 0.20084909 | A、B |

两种索引包含相同的可见文档，但排名相反。平均长度偏大，减轻了长文档 B 的长度惩罚。B 中的 `alpha` 出现 2 次，因此错误统计使 B 排在 A 前面。[复现条件及结果](https://github.com/apache/doris-thirdparty/pull/420)

**修复按目标索引和字段重新计算词元总数。** `mergeTerms()` 只累加具有有效目标行号的倒排记录。每条记录提供一个词元在一篇文档中的词频。代码把词频累加到对应目标索引的字段统计中。`mergeNorms()` 再把各自的统计值写入各自的目标索引。已删除文档不会进入累加，多个目标索引也会分别获得正确统计。[修复代码](https://github.com/Authorlove/doris-thirdparty/blob/f2864e07f08583b5cc948e87e82294fd0fd5de16/src/core/CLucene/index/IndexWriter.cpp#L1776)

**保存了 `norms` 却缺少词频的索引，通过重建获得准确总数。** `norms` 保存压缩后的文档长度信息。压缩会损失精度，例如长度 41 解码后可能是 40。因此，代码不能累加解码后的长度来获得准确总数。

如果索引保存了 `norms`，却没有保存词频，PR #420 会在创建目标写入器之前拒绝直接合并。配套 Doris PR #69313 为这类索引选择现有的重建路径。重建路径读取原始列数据，再建立索引。作者的对照测试显示，重建会增加合并耗时。[检查代码](https://github.com/Authorlove/doris-thirdparty/blob/f2864e07f08583b5cc948e87e82294fd0fd5de16/src/core/CLucene/index/IndexWriter.cpp#L1320)、[配套 Doris 修改](https://github.com/apache/doris/pull/69313)

作者报告 17 个 CLucene 测试通过。新增测试覆盖删除文档、多个目标索引、多个字段，以及缺少词频的情况。完整 Doris 集成验证仍待完成。[测试和验证范围](https://github.com/apache/doris-thirdparty/pull/420)

# 外部数据库下载脚本说明

本目录用于下载外部参考数据库数据，当前包含 3 个脚本：

- `download_bacdive.py`：按菌名查询 BacDive，并将结果保存为本地 JSON 文件。
- `download_bacdive_full.py`：按 BacDive ID 范围批量扫描，用于尽可能下载 BacDive 外部库的全量公开数据。
- `download_silva.py`：按指定直链下载 SILVA 发布文件。

这 3 个脚本的用途不同，不能混用。

## 1. BacDive 按菌名查询

脚本：`download_bacdive.py`

适用场景：

- 你已经有一批菌名。
- 你只想查询这些菌名在 BacDive 中是否有记录。
- 你想把外部数据作为本地数据库的补充，而不是下载 BacDive 整个库。

### 1.1 导出本地菌名查询文件

如果你希望把本地 `strain` 表中的学名导出来，生成一个查询名单：

```bash
python app/downloade/download_bacdive.py --export-strain-queries bacdive_queries.txt
```

执行后会生成：

```text
bacdive_queries.txt
```

这个文件里每一行是一个菌名。

### 1.2 按查询名单下载 BacDive 数据

```bash
python app/downloade/download_bacdive.py --query-file bacdive_queries.txt --out-dir data/bacdive --limit 100
```

### 1.3 参数含义

- `--query-file`
  含义：输入查询文件路径。
  说明：文件中每行一个菌名，例如 `Acinetobacter johnsonii`。

- `--out-dir`
  含义：输出目录。
  说明：每个菌名会保存成一个 JSON 文件。

- `--limit`
  含义：每个菌名最多保存多少条 BacDive 记录。
  说明：
  - `100` 表示每个菌名最多保存 100 条。
  - 这样可以避免像 `Escherichia coli` 这种命中过多，下载过慢或文件过大。

- `--username`
  含义：BacDive 用户名。
  说明：通常公共查询不一定需要，只有在你的环境确实需要认证时再传。

- `--password`
  含义：BacDive 密码。

- `--export-strain-queries`
  含义：把本地 `strain` 表中的菌名导出为查询文件。

### 1.4 终端输出如何理解

示例：

```text
[3/71] Querying BacDive: Acinetobacter johnsonii
  saved 29 record(s) -> data\bacdive\acinetobacter_johnsonii.json
```

含义：

- `3/71`：当前正在处理第 3 个查询词，总共有 71 个查询词。
- `saved 29 record(s)`：这个菌名在 BacDive 中下载到了 29 条记录。
- `data\bacdive\acinetobacter_johnsonii.json`：保存路径。

注意：

- `71` 不是 BacDive 全库总量。
- `71` 只是你输入文件里一共有 71 个菌名。

### 1.5 为什么有些菌名是 0 条结果

这通常是正常现象，不一定是脚本出错。常见原因：

- 该名称不是 BacDive 收录范围内的对象。
- 该名称不属于标准细菌双名。
- 该名称是复合群名，例如 `Acinetobacter calcoaceticus-baumannii complex`。
- 该名称属于真菌等非 BacDive 主要覆盖对象，例如部分 `Aspergillus`。

示例：

```text
saved 0 record(s)
```

表示该查询没有命中，不代表下载流程失败。

## 2. BacDive 外部库全量下载

脚本：`download_bacdive_full.py`

适用场景：

- 你不是想查自己已有的 71 个菌名。
- 你想尽可能把 BacDive 公共库整体下载到本地。
- 你后续准备离线筛选、清洗、入库。

这个脚本不是按菌名搜索，而是按 `BacDive ID` 连续扫描。

### 2.1 典型用法

```bash
python app/downloade/download_bacdive_full.py --out-dir data/bacdive_full --start-id 1 --end-id 300000 --batch-size 100 --stop-empty-batches 200
```

### 2.2 参数含义

- `--out-dir`
  含义：批量下载结果保存目录。

- `--start-id`
  含义：从哪个 BacDive ID 开始扫描。
  说明：通常从 `1` 开始。

- `--end-id`
  含义：扫描到哪个 BacDive ID 结束。
  说明：
  - 这是扫描上限，不代表 BacDive 一定有这么多 ID。
  - 如果上限设太小，可能会漏掉后面的记录。

- `--batch-size`
  含义：每批请求多少个 ID。
  说明：
  - `100` 表示每次请求 100 个连续 ID。
  - 批次越大，请求次数越少，但单次返回文件越大。

- `--stop-empty-batches`
  含义：连续多少个空批次后自动停止。
  说明：
  - “空批次”表示这一批 ID 没有下载到任何记录。
  - 例如设置 `200`，表示连续 200 批都为空时，脚本认为后续大概率没有更多公开记录了，于是停止。

- `--manifest`
  含义：进度清单文件路径。
  说明：用于记录当前跑到哪里，方便查看状态。

### 2.3 输出文件说明

输出目录示例：

```text
data/bacdive_full/
  bacdive_1_100.json
  bacdive_101_200.json
  bacdive_201_300.json
  manifest.json
```

说明：

- `bacdive_1_100.json`：表示扫描 ID 1 到 100 的结果。
- 每个批文件中只保存命中的记录。
- `manifest.json`：保存当前进度和统计信息。

### 2.4 终端输出如何理解

示例：

```text
Fetching ID range 1-100
  saved 96 record(s) -> data\bacdive_full\bacdive_1_100.json | ids 1..100
```

含义：

- `Fetching ID range 1-100`：正在扫描 BacDive ID 1 到 100。
- `saved 96 record(s)`：这一批中有 96 条真实记录。
- `ids 1..100`：返回结果覆盖的 ID 范围。

如果看到：

```text
empty batch
```

表示这一批连续 ID 没有下载到任何记录。

### 2.5 适合你的用法

如果你就是要“下载外部库本身”，应该使用：

```bash
python app/downloade/download_bacdive_full.py --out-dir data/bacdive_full --start-id 1 --end-id 300000 --batch-size 100 --stop-empty-batches 200
```

不要再用：

```bash
python app/downloade/download_bacdive.py --query-file bacdive_queries.txt ...
```

因为那个脚本只是“按菌名查询”，不是全库下载。

## 3. SILVA 文件下载

脚本：`download_silva.py`

适用场景：

- 你已经在 SILVA 网站上找到具体下载链接。
- 你要把某个 SILVA FASTA 或 taxonomy 文件下载到本地。

### 3.1 典型用法

```bash
python app/downloade/download_silva.py --url "https://www.arb-silva.de/fileadmin/silva_databases/current/Exports/SILVA_138.2_SSURef_NR99_tax_silva.fasta.gz" --out-dir data/silva
```

### 3.2 参数含义

- `--url`
  含义：SILVA 文件的直链地址。

- `--out-dir`
  含义：下载保存目录。

- `--filename`
  含义：强制指定输出文件名。
  说明：如果不传，脚本会从 URL 自动推断文件名。

示例：

```bash
python app/downloade/download_silva.py --url "..." --out-dir data/silva --filename SILVA_SSURef_NR99.fasta.gz
```

## 4. 推荐使用顺序

如果你的目标是“先把外部数据库下载下来，再补充本地菌库”，推荐顺序如下：

1. 先用 `download_bacdive_full.py` 下载 BacDive 全库公开数据。
2. 再用 `download_silva.py` 下载你需要的 SILVA 文件。
3. 下载完成后，再写入库脚本，把 JSON/FASTA 清洗后导入 MySQL。

## 5. 常见误区

### 误区 1

```text
[1/71]
```

不是表示 BacDive 全库只有 71 条。它只表示当前输入查询名单一共有 71 个菌名。

### 误区 2

`saved 0 record(s)` 不一定是错误。

它往往只是说明：

- 该菌名不在 BacDive 当前公开结果中。
- 该名称不是标准可检索学名。
- 该对象不属于 BacDive 主要覆盖范围。

### 误区 3

“按菌名查询”不等于“下载外部全库”。

这两件事分别对应：

- `download_bacdive.py`
- `download_bacdive_full.py`

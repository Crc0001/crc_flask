# 微生物识别模型 — 零分菌 & Staphylococcus 属混淆分析

> 基于 2026-07-16 验证结果 (173 张测试图, 45 种菌, 总体准确率 67.6%)

---

## 一、零分菌种 (5 种, 准确率 0%)

| 菌种 | 训练集 | 测试集 | 准确率 | 主混淆方向 |
|---|---|---|---|---|
| *Bacillus pumilus* | 35 张 | 4 张 | **0%** | → B. albus, A. melanogenum, S. ureilyticus |
| *Brevibacillus agri* | 31 张 | 3 张 | **0%** | → B. albus, A. melanogenum, B. manliponensis |
| *Bacillus manliponensis* | 27 张 | 2 张 | **0%** | → R. pickettii, B. cereus |
| *Brachybacterium paraconglomeratum* | 26 张 | 2 张 | **0%** | → A. seifertii |
| *Staphylococcus taiwanensis* | 25 张 | 2 张 | **0%** | → S. capitis, B. conglomeratum |

**关键发现：这 5 种菌的训练集数量并不少 (25-35 张)，但全部来自同一拍摄批次。BioCLIP 学到的不是菌落形态，而是那一批次的背景/光照，换一批就全崩。**

### B. pumilus 详细分析

4 张测试图中，正确答案 B. pumilus 仅在 Top-3 中出现 1 次（且仅排第 2，21% 置信度）。模型对它完全"失明"。

```
IMG_161749: pred=A. melanogenum(16%)  → B. pumilus 未进 Top-3
IMG_161751: pred=R. pickettii(16%)    → B. pumilus 未进 Top-3
IMG_161753: pred=B. albus(18%)        → B. pumilus 未进 Top-3
IMG_161802: pred=S. ureilyticus(40%)  → B. pumilus 在 Top-3 第 2 位 (21%)
```

### Brevibacillus agri 详细分析

3 张测试图，Brevibacillus agri 仅在 Top-3 出现 1 次（排第 3，9%）。

```
IMG_162037: pred=B. albus(22%)          → B. agri 在 Top-3 第 3 位 (9%)
IMG_162039: pred=B. manliponensis(8%)   → B. agri 未进 Top-3
IMG_162042: pred=A. melanogenum(13%)    → B. agri 未进 Top-3
```

---

## 二、准零分菌种 (准确率 ≤33%)

| 菌种 | 训练集 | 测试集 | 准确率 |
|---|---|---|---|
| *Staphylococcus hominis* | 30 张 | 7 张 | **14.3%** (1/7) |
| *Staphylococcus epidermidis* | 22 张 | 5 张 | **20.0%** (1/5) |
| *Staphylococcus petrasii* | 23 张 | 5 张 | **20.0%** (1/5) |
| *Pantoea ananatis* | 19 张 | 3 张 | **33.3%** (1/3) |
| *Pseudescherichia vulneris* | 24 张 | 3 张 | **33.3%** (1/3) |
| *Serratia marcescens* | 30 张 | 3 张 | **33.3%** (1/3) |

---

## 三、Staphylococcus 属内战 (8 种, 平均准确率 45%)

| 菌种 | 训练 | 测试 | 准确率 | 主要被误认成 | 主要误认来源 |
|---|---|---|---|---|---|
| S. ureilyticus | 33 | 3 | **100%** ✅ | — | S. hominis |
| S. cohnii | 24 | 7 | **71.4%** | S. petrasii, B. cabrialesii | — |
| S. capitis | 21 | 7 | **71.4%** | S. taiwanensis | S. taiwanensis, S. petrasii, S. hominis |
| S. roterodami | 25 | 2 | **100%** ✅ | — | A. lwoffii |
| S. hominis | 30 | 7 | **14.3%** | S. ureilyticus, S. taiwanensis, S. maltophilia | — |
| S. epidermidis | 22 | 5 | **20.0%** | E. quasihormaechei, A. oryzae | — |
| S. petrasii | 23 | 5 | **20.0%** | S. capitis, B. agri | S. cohnii |
| S. taiwanensis | 25 | 2 | **0%** | S. capitis, B. conglomeratum | S. capitis |

**混淆矩阵密集区：**

```
S. capitis ←→ S. taiwanensis     (双向混淆, 各 2 次)
S. hominis  → S. ureilyticus    (单向, 2 次)
S. hominis  → S. maltophilia    (单向, 1 次)
S. cohnii   → S. petrasii       (单向, 1 次)
```

**结论：Staphylococcus 属 8 种的 BioCLIP 特征高度重叠。** 菌落形态差异对 ViT-B/16 来说区分度不够。

---

## 四、补数据优先级

### 🔴 第一优先 (零分菌, 5 种)

每种至少补 **20 张新图**，要求：
- 至少分 **2 个不同批次/日期** 拍摄
- 至少用 **2 种不同培养基** 或 **不同光照条件**
- 如果可能，换一台设备拍一部分

| 顺序 | 菌种 | 当前训练 | 当前测试 | 目标新增 |
|---|---|---|---|---|
| 1 | *Bacillus pumilus* | 35 | 4 | ≥20 (2批次) |
| 2 | *Brevibacillus agri* | 31 | 3 | ≥20 (2批次) |
| 3 | *Bacillus manliponensis* | 27 | 2 | ≥20 (2批次) |
| 4 | *Brachybacterium paraconglomeratum* | 26 | 2 | ≥20 (2批次) |
| 5 | *Staphylococcus taiwanensis* | 25 | 2 | ≥20 (2批次) |

### 🟡 第二优先 (准零分菌, 6 种)

| 顺序 | 菌种 | 当前训练 | 当前测试 | 目标新增 |
|---|---|---|---|---|
| 6 | *Staphylococcus hominis* | 30 | 7 | ≥30 (多批次) |
| 7 | *Staphylococcus epidermidis* | 22 | 5 | ≥30 (多批次) |
| 8 | *Staphylococcus petrasii* | 23 | 5 | ≥30 (多批次) |
| 9 | *Pantoea ananatis* | 19 | 3 | ≥15 |
| 10 | *Pseudescherichia vulneris* | 24 | 3 | ≥15 |
| 11 | *Serratia marcescens* | 30 | 3 | ≥15 |

### 🟢 第三优先 (Staphylococcus 专项)

将整个 Staphylococcus 属 (8 种) 作为一个专项数据集，统一再拍一轮：
- 同一批培养条件下同时拍 8 种，让光照/背景一致
- 这样模型必须从菌落形态区分，不能靠背景取巧
- 目标：每种新增 ≥20 张（同批次），另每个关键种加 ≥10 张（不同批次）

---

## 五、预期效果

| 补完第一优先 | 总体准确率估计 | 说明 |
|---|---|---|
| 当前 | **67.6%** | 基线 |
| 补 5 种零分菌 | **~75-78%** | 这 5 种目前贡献了 13 张全错 |
| 补 Staphylococcus | **~82-85%** | Staphylococcus 贡献了 23 张错 |
| + 正则化参数调优 | **~87-90%** | 算法层面压缩过拟合 |

---

生成时间: 2026-07-16 19:02 GMT+8

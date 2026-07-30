# BioCLIP + XGBoost 菌落分类器

## 安装依赖（一次性）

```powershell
C:\Python312\python.exe -m pip install xgboost scikit-learn pillow --quiet
```

## 第1步：准备训练数据

在 `data\train\` 下按菌种建子目录，每个目录放该菌种的照片：

```
bioclip_xgboost\
  data\
    train\
      大肠杆菌\
        IMG_0001.jpg
        IMG_0002.jpg
        ...（每类至少 10-20 张，越多越好）
      金黄色葡萄球菌\
        IMG_0101.jpg
        ...
      铜绿假单胞菌\
        ...
```

⚠️ **数据质量最关键**：
- 所有照片尽量在**相同的拍照条件**下拍（同一台相机/手机、相同距离、相同光照）
- 如果拍照条件变化大，准确率会掉——因为模型会学会"认背景"而不是"认菌"
- 每类菌的理想数量：**≥30 张**。太少效果差是正常的

## 第2步：训练

```powershell
cd C:\Users\17300\.openclaw\workspace\bioclip_xgboost
C:\Python312\python.exe train_classifier.py train
```

训练过程：
1. BioCLIP 提取每张照片的 768 维特征向量（= 分光光度计测吸光度）
2. XGBoost 学习特征→菌种名的映射（= 拟合标准曲线）
3. 模型保存在 `model\` 目录

## 第3步：预测新照片

```powershell
C:\Python312\python.exe train_classifier.py predict 你拍的新菌落照.jpg
```

输出示例：
```
🔬 预测结果: IMG_9999.jpg
==================================================
  1. 大肠杆菌          87.3%  [██████████████████████████░░░░]
  2. 金黄色葡萄球菌       8.1%  [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
  3. 铜绿假单胞菌         3.2%  [█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]

  🟢 高置信度 → 可直接出具报告
```

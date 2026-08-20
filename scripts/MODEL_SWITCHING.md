# 菌种识别模型替换说明

菌种识别由 `app/services/yolo_service.py` 负责加载，YOLO 仍然只负责框选菌落。

## 当前默认模型

当前默认使用：

```text
HwishAI/bioclip_hc_euclidean_vit_b16/
```

服务读取以下文件：

```text
HwishAI/<模型目录>/model/metadata.json
HwishAI/<模型目录>/model/xgb_<类别数>.json
```

`metadata.json` 必须包含：

- `encoder.model_ref`：BioCLIP 编码器名称
- `encoder.embedding_normalization`：`raw` 或 `l2`
- `class_count`：类别数量
- `classes`：与 XGBoost 输出顺序一致的菌种名称列表

## 临时切换模型

在启动 Flask 服务的同一个 PowerShell 窗口执行：

```powershell
$env:HWISHAI_CLASSIFIER_MODEL = "biocap_vit_b16"
python run.py
```

换回当前默认模型：

```powershell
$env:HWISHAI_CLASSIFIER_MODEL = "bioclip_hc_euclidean_vit_b16"
python run.py
```

环境变量的值是 `HwishAI` 下的模型目录名，不是模型文件路径。

## 永久切换模型

写入当前 Windows 用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable(
    "HWISHAI_CLASSIFIER_MODEL",
    "biocap_vit_b16",
    "User"
)
```

设置后需要关闭并重新打开终端，再重启 Flask 服务。删除永久配置、恢复代码中的默认模型：

```powershell
[Environment]::SetEnvironmentVariable(
    "HWISHAI_CLASSIFIER_MODEL",
    $null,
    "User"
)
```

## 添加新模型

1. 把新模型目录放到 `HwishAI/` 下。
2. 确认目录内存在 `model/metadata.json` 和 XGBoost JSON 文件。
3. 将 `HWISHAI_CLASSIFIER_MODEL` 设置为新目录名。
4. 重启 Flask 服务。
5. 用已知菌种图片检查预测类别、置信度和类别中文名是否正常。

模型在进程内只加载一次，因此仅修改环境变量而不重启服务不会生效。

第一次使用某个新编码器时，`open_clip` 会根据 `metadata.json` 中的
`encoder.model_ref` 下载并缓存对应权重；之后可直接使用本地缓存。
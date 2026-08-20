# 客户部署清单（半自动工具包）

> 部署方式：我们远程桌面操作（需客户给管理员权限）。装完是 Windows 服务，
> 开机自启、崩溃自动拉起；用户只需双击桌面【AI菌种分析系统】快捷方式使用。
> 客户机器要求：Windows 10/11 x64，4核8G 以上，已装 MySQL 8（未装则先装 Server 组件）。

## 一、打包（我方机器，一次性）

- [ ] 运行 `deploy_client\00_prepare_vendor.ps1`（下载 Python 安装包 / NSSM / 离线依赖到 `vendor\`）
- [ ] 运行 `deploy_client\build_package.ps1` → 生成 `dist\hwishai_client_deploy\`
- [ ] 检查：`vendor\nssm\nssm.exe`、`vendor\python\python-3.12.10-amd64.exe`、`vendor\wheels\*.whl` 齐全
- [ ] 我方 vendor 服务已配置好该客户的机器令牌（`HWISHAI_VENDOR_TOKENS`），且外网出口可用

## 二、安装（客户机器，远程桌面，管理员权限）

- [ ] 拷贝 `dist\hwishai_client_deploy\` 到客户机器（如 `D:\hwishai_pkg`）
- [ ] 确认已装 MySQL 8，记住 root 密码；确认 8856 端口未被占用
- [ ] 运行 `01_install_python.bat`（静默装 Python 到 `C:\HwishAI\Python312`）
- [ ] 运行 `02_create_venv.bat`（建 venv + 离线装依赖，全程不联网）
- [ ] 把包内代码拷到 `C:\HwishAI\`：`app\`、`run_client.py`、`requirements-client.txt`、`init_empty_db.sql`、`03_init_mysql.py`、`04_configure.py`
- [ ] 运行 `python 03_init_mysql.py`（建空库 `crc_ai` + 应用账号 + 空表结构，**零数据**）
- [ ] 运行 `python 04_configure.py`（填我方 API 地址、机器令牌、数据库密码、客户管理员账号密码）
- [ ] 运行 `05_install_service.bat`（NSSM 注册服务 + 开机自启 + 崩溃重启 + 防火墙 8856 + 桌面快捷方式）
- [ ] 运行 `06_install_backup_task.bat`（注册每日 02:30 数据库自动备份，并立即执行一次验证）
- [ ] 检查 `C:\HwishAI\backups\` 出现 .sql 备份文件且 >0 KB；任务计划程序里能看到 `HwishAIDbBackup`
- [ ] 浏览器打开 `http://127.0.0.1:8856/` 确认登录页出现

## 三、账号（现场与客户一起）

- [ ] 用客户管理员账号登录（首登强制改密），确认侧边栏能看到【管理控制台】
- [ ] 管理控制台四个页面可用：概览 / 用户管理 / 权限管理 / 操作日志
- [ ] 客户管理员创建操作员账号（用户名/密码由客户定）
- [ ] 确认客户管理员看不到 `hwishai` 账号；`hwishai` 能管理全部账号
- [ ] 权限管理：给某操作员去掉"菌种检测"权限 → 该操作员侧边栏不再显示入口、直接访问提示 403
- [ ] 告知客户：系统全新，样品/菌种库/趋势均无数据，从第一笔检测开始积累

## 四、验收清单

- [ ] 重启客户机器 → 服务自动启动，双击桌面快捷方式能直接打开系统（无需任何手动启动）
- [ ] 登录 / 退出 / 改密 / 失败锁定 正常
- [ ] 功能1 菌种检测：上传图片 → 返回 Top3（走我方 API）→ 结果图显示 → 保存报告 → 导出 PDF
- [ ] 功能2 菌种数据库：保存的报告出现在列表，可编辑/删除
- [ ] 功能3 趋势分析：有数据后图表正常
- [ ] 功能4 知识库：搜索/详情正常（走我方 API）
- [ ] 远程调用：客户系统用账号 Token 调 `/api/v1/recognize`、`/api/v1/knowledge/search` 正常，错误 Token 返回 401
- [ ] 局域网其它电脑通过 `http://客户机IP:8856/` 可访问

## 五、运维备忘

- 服务名 `HwishAIStrain`；日志 `C:\HwishAI\logs\service*.log`
- **服务账户**：05_install_service.bat 会自动创建低权限本地账户 `hwishai_svc`（随机密码、仅服务登录）
  并以该账户运行服务（不再以 SYSTEM 运行）；该账户对 `C:\HwishAI` 有读写权限。
- **数据库备份**：每日 02:30 自动执行（任务 `HwishAIDbBackup`），备份在 `C:\HwishAI\backups\`，
  保留 30 天，执行记录 `backup.log`。恢复：`mysql -u<用户> -p crc_ai < crc_ai_日期.sql`
- 停/卸载：包内 `service_stop.bat`、`service_uninstall.bat`；或 `services.msc` 里操作
- 改配置：`C:\HwishAI\instance\config.py` 改完重启服务生效
- 升级：停服务 → 替换 `C:\HwishAI\app\` 与 `run_client.py` → 起服务

## 六、已知注意点

- **采样地点分类（sample_lite）初始为空**：检测页"采样地点"下拉在客户提供分类前没有选项——
  页面已支持"分类未配置时可不填"；等客户提供地点分类表后导入即可恢复必填下拉。
- 结果图片放在 `C:\HwishAI\app\static\results\`，内网可直读；如需更严权限控制另行加固。
- 机器令牌与账号 Token 均为长期凭据：泄露后在我方删除对应白名单令牌/在账户管理里重置 Token 即可。
- 上传限制：图片仅支持 png/jpg/jpeg/bmp/webp，单文件 ≤20MB（扩展名+魔数+尺寸三重校验），
  超限或伪造文件会被拒绝；MALDI TXT 单文件 ≤2MB。

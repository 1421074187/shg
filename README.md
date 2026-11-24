# NbOCl₂ 堆叠 SHG

计算 NbOCl₂ / hBN / NbOCl₂ 结构在法向入射下的反射二次谐波。网页可查看厚度图、Stokes 参数和线检偏瓣图，也可输入上下两片各自的复折射率、非线性系数和转角重新计算。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `public/` | 网页、交互脚本和默认厚度扫描数据 |
| `app.py` | Flask 网页入口及 `/api/bootstrap`、`/api/calculate` 接口 |
| `shg/` | 模型、传播求解器、材料参数和扫描数据来源记录 |
| `desktop/launch.py` | 可选的本地桌面启动器 |
| `requirements.txt`、`.python-version`、`vercel.json` | Python 依赖、版本和 Vercel 配置 |

默认厚度扫描从 `public/data/baseline_maps.json` 读取，由 Vercel CDN 提供。Flask 接口提供初始化信息和自定义计算结果。

## 本地运行

本地运行需要 64 位 Python 3.12。安装后，在 Windows PowerShell 中运行以下命令。

```powershell
Set-Location -LiteralPath 'D:\Desktop\git'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run
```

打开 `http://127.0.0.1:5000/`。预期首页显示两张默认厚度图。切换 hBN 厚度并拖动上下层厚度滑块，图和 Stokes 表应随之更新。把下层转角改为 85° 后点击「计算并更新厚度图」，预期页面显示「自定义计算 · 条件预测」，结果标签显示 85°。若失败，记录浏览器里对应请求的状态码，以及 PowerShell 中的错误输出。

需要桌面启动窗口时，在仓库根目录运行 `.\.venv\Scripts\python.exe -m desktop.launch`。桌面启动器使用 Python 自带的 Tkinter。

## GitHub 和 Vercel

1. 将本目录作为 GitHub 仓库根目录提交。
2. 在 Vercel 导入该仓库，根目录保留仓库根目录，框架预设选择 **Flask**。
3. 保留默认的安装命令、构建命令和输出目录，然后部署。打开部署地址，重复上面的网页验证步骤。

[Vercel Flask 部署文档](https://vercel.com/docs/frameworks/backend/flask)

## 模型范围

上下层 NbOCl₂ 扫描 20–200 nm，hBN 扫描 30–100 nm，步长为 5 nm，另含 0 nm 对照。结果以历史 75.4 nm 单片 NbOCl₂ 的反射 SHG 强度作固定参考。默认折射率沿用历史输入，非线性系数是相对值。模型给出法向入射条件下的计算预测。

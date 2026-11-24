# pdfdev · 版式还原用的量尺

这三个脚本是「把一份成品简历 PDF/图片还原成 Word 版式」时用的量具，不参与运行时生成，
只用于**核对新模板还原得像不像**。

```powershell
$py = "D:\...\resources\office-runtime\primary-runtime\dependencies\python\python.exe"

# 1) 把 PDF 拆成布局 JSON（文字坐标/字号/颜色、色块、图片），第三参数给个目录会把内嵌图导出来
& $py tools\pdfdev\pdf_probe.py 模板.pdf out\layout.json out\imgs

# 2) 按坐标粗略重绘成 PNG，用肉眼比排版（不是高保真渲染器，只用来对位置）
& $py tools\pdfdev\pdf_render.py out\layout.json out\preview.png 2 out\imgs

# 3) 把「模板 layout」和「自己生成的 layout」逐行对表，输出 dy/dx 偏差
& $py tools\pdfdev\compare.py out\模板-layout.json out\生成-layout.json out\diff.txt
```

`compare.py` 的 dy 定义是 `我方 y − 模板 y`：PDF 坐标是左下原点，**dy 为正 = 我方更靠上**。

核对结果示例见 `docs/verification/dark-blue-vs-template.txt`：主栏逐行误差 ≤ 0.1pt。

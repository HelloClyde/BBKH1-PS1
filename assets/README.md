`icon.png` 是使用内置 imagegen 重新设计的 PSX 图标：H1 风格的青蓝高光圆角底板、灰色光盘主机和手柄，以及清晰的 PSX 标识。参考本机 H1 桌面及现有 GBA/FC 图标的立体、高光和渐变风格，没有复制原机图标的像素。底板外缘为真正的透明背景。

生成提示词见 [icon-prompt.txt](icon-prompt.txt)，来源与 SHA-256 见 [icon.provenance.json](icon.provenance.json)。图标随项目按 GPL-2.0-or-later 分发。普通构建直接读取已收录 PNG；不调用图像服务，也不会用旧的几何图标生成器覆盖它。

固定 SDK 在构建时将 PNG 转换为四份 H1 原生图标资源：45×45、57×57 的 RGB565+alpha，以及两份 49×60 的 RGB565。两份带 alpha 的资源保留透明外缘，其余按 H1 格式处理。HUD 的 3×5 字形直接定义在 hud.c 中，无外部字体依赖。

暂停菜单使用 Noto Sans CJK SC Regular 的 18×21 位图字形子集，采用 SIL OFL 1.1，许可见 licenses/NotoSansCJK-OFL.txt。字体来源 notofonts/noto-cjk 固定提交 f8d157532fbfaeda587e826d4cd5b21a49186f7c，文件 Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf，SHA-256 为 2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b。普通构建直接使用 src/menu_font.h，不需要安装字体。不分发原始 OTF 文件。

取得上述固定版本字体后，使用 `python tools/generate_menu_font.py --font 路径/NotoSansCJKsc-Regular.otf` 再生。字体适用 OFL；PS1 图标与代码仍适用各自原有许可。

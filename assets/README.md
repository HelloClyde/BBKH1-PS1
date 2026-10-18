图标由原创几何图形和 PS1 文字绘制，采用本项目 GPL-2.0-or-later。默认构建使用已收录 PNG；可用 `python tools/make_assets.py --regenerate-icon` 以 Pillow 默认字体再生。HUD 的 3×5 字形直接定义在 hud.c 中，无外部字体依赖。

暂停菜单使用 Noto Sans CJK SC Regular 的 18×21 位图字形子集，采用 SIL OFL 1.1，许可见 licenses/NotoSansCJK-OFL.txt。字体来源 notofonts/noto-cjk 固定提交 f8d157532fbfaeda587e826d4cd5b21a49186f7c，文件 Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf，SHA-256 为 2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b。普通构建直接使用 src/menu_font.h，不需要安装字体。不分发原始 OTF 文件。

取得上述固定版本字体后，使用 `python tools/generate_menu_font.py --font 路径/NotoSansCJKsc-Regular.otf` 再生。字体适用 OFL；PS1 图标与代码仍适用各自原有许可。

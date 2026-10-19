# 来源与许可记录

- PCSX4ALL 固定为 `dmitrysmagin/pcsx4all` 提交 `c7faf12b893eba94faced88baa5e7dd059be58b7`。核心文件保留 GPL-2.0-or-later 等原始声明；仓库附带的 `gpl.txt` 是 GPL v3 文本。MIPS 重编译器保留 Ulrich Hecht、Dmitry Smagin、Daniel Silsby 等人的 MIT 声明。GPU、SPU、GTE、HLE 等组件以各自文件头为准。
- zlib 固定为 v1.3.1，提交 `51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`，保留 `LICENSE` 及原始版权声明。
- H1 SDK 固定为 `MrDefinition1999/bbk-h1-bda-sdk` 提交 `067fe072477861dfc8949d7b1a55279fb92d2548`，使用其 Apache-2.0 `LICENSE` 与 `NOTICE`。
- 本目录的 H1 适配、新增工具、等待循环识别器和原创 PS-X EXE 测试以 GPL-2.0-or-later 提供；修改上游文件的代码保留原有许可。PSX 图标使用内置 imagegen 原创生成并按 GPL-2.0-or-later 随项目分发，来源及提示词见 assets/，未复制 Sony 官方图标素材。
- `src/libc.c`、初始 freestanding 头文件、启动入口、PCM 和输入适配沿用了父工作区的 H1 实现。其初始 libc 来自 `HelloClyde/BBK9588-gba` 提交 `57c2792ec374b394df24c0ee898bb8624cf95a85`，父工作区记录为 GPL-2.0；原始来源声明仍适用。本仓库保留 GPL v2 全文；该来源仅适用于派生的运行时和测试模型，不引入 GBA/GB 核心。
- GNU 工具链是外部构建依赖，不包含在安装包中。
- BIOS、游戏镜像、BBK 固件与从游戏提取的文件不随包提供。FF7 与山脊赛车只使用用户已有本地文件测试，未上传到外部服务。

完整上游网址、提交与构建前校验见 `UPSTREAM.json`；依赖的原始声明保留在各固定版本源码中。本项目不主张拥有上游软件或相关商标。

- `tests/support/` 的 H1 服务模型来自同一 H1 工作区，沿用 GPL-2.0。它只模拟服务表与内存，不包含 BBK 固件。

- PS1 触屏暂停菜单沿用同一 H1 工作区 GBA 菜单的操作和绘制方式，适配代码以 GPL-2.0-or-later 提供。中文位图字形来自 Noto Sans CJK SC（OFL 1.1），见 `assets/README.md` 与 `assets/licenses/NotoSansCJK-OFL.txt`；字体不适用项目 GPL。

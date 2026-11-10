# nx2android · MTK / Mali 分支

> **nx2android-mtk** 是 [nx2android](https://github.com/shirai91/nx2android) 的 **MediaTek + Arm Mali 适配分支**：让 Switch 移植能在天玑（Dimensity）/ Mali GPU 的安卓设备上跑起来。
> 已在 **Redmi K50（天玑 8100，Mali-G610 MC6，Android 13）** 上验证：*《神之亵渎 2》(Blasphemous 2)* 稳定 30–40 fps 可玩。
>
> English: the MediaTek/Mali adaptation of nx2android. Ports run on Arm Mali GPUs and MediaTek's Vulkan drivers; the porter and the graphics core are upstream's, the Mali work is described in [docs/MALI.md](docs/MALI.md).

它把 Switch 游戏**自己的 arm64 代码**跑在安卓上：用一个宿主顶替 Switch 的系统服务，把 NVN 图形调用重放到 Vulkan。选游戏文件夹、点 **Port**，得到 APK + 游戏数据，插上设备还能直接安装。

自备游戏文件与 `prod.keys`（从你自己的 Switch 导出）。本仓库和它的发布物都不含任何游戏内容或密钥。

iOS / iPadOS 的同源项目：[nxnative](https://github.com/seedds/nxnative)。

---

## 这个分支改了什么

上游只针对 Adreno / Xclipse。Mali 的结构不一样（tile-based 渲染、没有 BC 纹理压缩、gralloc 行为不同），这个分支专门补这些：

| 问题 | Mali 上的表现 | 修法 |
|---|---|---|
| **没有 BC 纹理压缩** | Switch 游戏纹理是 BC 格式，Mali 直接不认 | 上传时在 CPU 解码成 RGBA8 / R8 / R8G8 / RGBA16F，解码后的显存由 `DM_VK_BC_MAX_MB` 限制；采样字节数是主机的 4–8 倍，所以建议 8GB 内存以上 |
| **gralloc 句柄带多个 fd** | 只认第一个 fd → 所有内存池退化成"每帧整块拷贝" → **600ms 一帧、2 FPS、黑屏** | 逐个尝试句柄里的每个 fd，找到真正能 mmap 的 dma-buf（天玑上是第 2 个） |
| **CPU 写入对 GPU 不可见** | 偶尔整个网格被拉成横贯屏幕的细线（约每秒一次） | 每次提交前对**游戏写过的那部分共享内存**做 `dc civac`（clean+invalidate），用 mprotect 脏页跟踪，只刷写过的 64KB 块 |
| **旧款 Mali 采样器上限低** | Bifrost 上每 stage 只有 16 个 | 超出时在日志里点名，方便定位是哪个 shader |
| **边框色 / 线性过滤差异** | 缺 `customBorderColorWithoutFormat`；部分格式不支持线性过滤 | 边框色退回透明黑并记录；不支持线性过滤的采样改绑 nearest |
| **CPU 侧热点** | 抢占判断每次读 `/proc`、池销毁整块拷回 | 线程状态 1ms 缓存；池 finalize 后保留映射不再拷回 → 菜单 30 fps → 40 fps |

原理、日志含义、真机验证步骤：**[docs/MALI.md](docs/MALI.md)**。

## 已测试

| 游戏 | 设备 | 状态 |
|---|---|---|
| Blasphemous 2（1.0.8） | Redmi K50 · 天玑 8100 · Mali-G610 MC6 | 存档点场景 30–40 fps；标题、菜单、过场、教学、战斗正常；内存池零拷贝、无拉伸伪影 |

Adreno / Xclipse 设备请用[上游](https://github.com/shirai91/nx2android)：支持的游戏更多、也更稳。

## 需要什么

- 一台 **Windows PC** 或 Apple silicon 的 Mac（约 30GB 空闲：工具链 4GB，一个移植约等于游戏体积的两倍）
- 一台安卓设备：**Mali GPU**（联发科天玑、部分 Exynos）。建议 **8GB 内存以上**
- 游戏本体（NSP / XCI / NSZ / XCZ，含更新与 DLC）和你的 **`prod.keys`**

## 快速开始

1. 装 Python 3.11+ 与依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 启动图形界面：

   ```bash
   python -m gui
   ```

   命令行等价：`python -m porter port <游戏文件夹> -k <prod.keys> --install`

3. **Setup** 页：点 **Download missing tools**（Android NDK r27c、.NET SDK、platform-tools，约 1GB），再选 `prod.keys`，全部变绿。
4. **Port** 页：选游戏文件夹 → **Port**。勾选 **Install on the device when done** 可直接装到插着 USB 的设备上。

详细步骤与常见问题：[packaging/INSTALL.md](packaging/INSTALL.md)。

### 在 Mali 设备上首次运行要看什么

游戏数据目录里的 `log.txt` 会自报能力（`adb pull /sdcard/Android/data/<包名>/files/log.txt`）：

```
[vk] GPU Mali-G610 MC6 (vendor 0x13b5), Vulkan 1.1.177, driver 32.1.0
[vk] GPU family: ARM Mali; a stage may bind 500000 samplers, ...
[vk] ... BC no (decoded on the CPU), ASTC yes, ...
[vk] zero-copy: the buffer's dma-buf is fd 1 of 3 (the handle carries others that do not map)
[vk] CPU cache maintenance (dc civac) available: the pools are cleaned before each submission
```

以 `[RED]` 开头的行就是需要查的地方，每条的含义都写在 [docs/MALI.md](docs/MALI.md)。

## 从源码

```bash
pip install -r requirements.txt
python -m gui                 # 图形界面
python -m porter --help       # 命令行
python -m unittest discover tests
```

打包玩家版需要 PySide6、PyInstaller，并且 Windows 上要先编译 PyInstaller 的 bootloader（需要 MSVC Build Tools）：

```bash
python packaging/build_bootloader.py
python packaging/build_bundle.py
```

## 已知问题

- **30 fps 是这颗 GPU 的上限，不是 bug**：单帧 GPU 时间约 26ms（43 个全屏 pass、1080p 目标），60 fps 需要 16.6ms。想更快只能按游戏削减后处理或降内部分辨率（per-game 工作）。
- 部分特性 Mali 不支持（32 位浮点的线性过滤、某些 advanced blend mode），会退回近似实现，个别特效观感可能不同。
- 目前只验证过一款游戏。新游戏出问题时，`log.txt` 里的 `[RED]` 行通常能直接指出方向。

## 致谢与许可

- 上游：[shirai91/nx2android](https://github.com/shirai91/nx2android) —— 移植工具与图形核心
- iOS 同源：[seedds/nxnative](https://github.com/seedds/nxnative)
- 许可：MIT，见 [nxnative/LICENSE](nxnative/LICENSE)；第三方代码各自沿用其许可

本项目不提供也不下载任何游戏文件或密钥。用你自己的卡带/数字版导出，风险与合法性取决于你所在地区。

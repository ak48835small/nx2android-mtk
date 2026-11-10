# Mali (MediaTek Dimensity, Arm Immortalis)

A port replays NVN on Vulkan, and a Switch game's renderer assumes what the console's GPU has. The Adreno GPUs the games were brought up on meet those assumptions; Arm's Mali (in every Dimensity and Helio) does not, and MediaTek's drivers add a few of their own. This is what the host does about it, what it says in the log, and how to bring a port up on such a device.

**Status (2026-11-10).** Blasphemous 2 runs on a **Redmi K50 (Dimensity 8100, Mali-G610 MC6, Android 13)**: title screen, main menu, a new pilgrimage and its opening cinematic's subtitles, at 30-40 fps (the frame-rate governor settles at 30-40, GPU 15-20 ms a frame). The cinematic's **video is black** while its subtitles draw (see "What is not done"). Before this session no Mali device had run a port at all.

## What Mali lacks, and what the replay does

| Mali | The replay's assumption | What the host does now |
|---|---|---|
| No BC textures (`textureCompressionBC` off) | BC1-BC7 are sampled as they are, as on the console | Decodes them on the CPU at upload into RGBA8 (BC1, BC2, BC3, BC7), R8 (BC4), R8G8 (BC5) or RGBA16F (BC6H): `gfx_vk_tex.c` `bc_decode`. 2 to 8 times the guest's bytes in the device's memory, bounded by `DM_VK_BC_MAX_MB`. Measured: the menus and the world's textures come out right |
| No custom border colour without a format (`customBorderColorWithoutFormat` off) | A sampler carries any border colour, in `VK_FORMAT_UNDEFINED` | A colour that is not transparent black, opaque black or white falls back to transparent black, and the first 8 are logged `[RED]` (`make_sampler`) |
| No linear filtering of some formats (32-bit float) | A game's linear sampler over one is legal | Such samples take the sampler's nearest twin, as integer views already did (`vk_fmt_linear`, `tex_desc_for`), logged once |
| Vulkan 1.1 (G610, driver 32.1.0), no `VK_KHR_dynamic_rendering`, no `VK_EXT_robustness2`, no `VK_EXT_depth_clip_control`, no display timing | Dynamic rendering, `nullDescriptor`, depth clip control, `VK_GOOGLE_display_timing` | All were already optional: render pass objects, dummy views, the host's own clip, and frame pacing on the fences. Nothing to do but say so in the log |
| Descriptor limits: **not** a problem on Valhall (the G610 reports 500000 of every per-stage descriptor kind) | — | The per-stage limit check in `gfx_vk_shader.c` stays as a warning for older Bifrost GPUs, where the limits are far lower |
| MediaTek's gralloc hands an AHardwareBuffer's handle over with **several fds**, and only one of them is the mappable dma-buf | The first fd is the dma-buf, as on Adreno | `pool_zero_copy` tries every fd the handle carries (the G610: three, of which the second maps) |
| Frame pacing through `VK_GOOGLE_display_timing`, GPU clocks through KGSL | Present on Adreno | Both already optional: a missing display-timing extension paces on the fences, and `/dev/kgsl-3d0` is simply not there (`perf_android.c`) |

## Zero copy is what makes it playable

A pool's pages become an AHardwareBuffer's and are mapped at the guest's address, so the game's own memory is the GPU's: no per-submission copy, no dirty-page tracking. On the G610 the first fd of the handle answers `EPERM` and the third `EINVAL`; the second one maps. Before `pool_zero_copy` tried them all, every pool was copied, and because a copied pool makes each submission wait for the GPU to finish the one before (`mtl_sub_begin`), frames took **600 ms** with the GPU 1-10 ms busy — 2 fps, black picture. With the dma-buf found, frames take 17-20 ms. This is the single most important Mali difference found so far, and it is invisible unless the log says which fd mapped:

```
[vk] zero-copy: the buffer's dma-buf is fd 1 of 3 (the handle carries others that do not map)
[vk] memory pool 0x734b000000 +0x2001000: zero-copy (zero-copy 32.3 MB, copied 0.0 MB)
```

## What the log says

The first lines after the device names itself are a report, so a log from a phone is enough to know what the driver offers:

```
[vk] GPU Mali-G610 MC6 (vendor 0x13b5, device 0xa8670000), Vulkan 1.1.177, driver 32.1.0 (0x8001000)
[vk] GPU family: ARM Mali; a stage may bind 500000 samplers, 500000 sampled images and 500000 storage images (500000, 500000 a set); 2D images up to 32768, 4294967295 allocations
[vk] device has no VK_EXT_robustness2
[vk] device has no VK_EXT_depth_clip_control
[vk] Vulkan 1.1 device: 25 extensions enabled for the features promoted to 1.2 / 1.3; dynamic rendering no (render pass objects only)
[vk] Mali-G610 MC6, Vulkan 1.1, driver 0x8001000; timeline semaphores yes, BC no (decoded on the CPU), ASTC yes, geometry shaders yes, nullDescriptor no, custom border colours yes, depth clip control no, transform feedback yes; pipeline cache 0 bytes
[vk] texture format 0x41 (VkFormat 137): the device has no BC textures, decoded on the CPU into VkFormat 37
```

While playing, one line every 3000 presents (about 75 s at 40 fps) says what the decoded textures cost:

```
[vk] BC textures decoded on the CPU: 812 MB in 4310 images now (budget 2048 MB), 4310 decoded so far in 2.4 s, 120 MB dropped
```

A drop line means the budget was reached and textures are being decoded again and again: raise `DM_VK_BC_MAX_MB` if the device has the memory, or accept the hitching.

## Trying a port on a Dimensity device

1. Port a light game first (Unpacking, Celeste, 13 Sentinels), not Tears of the Kingdom: the BC decode cost is what is being measured, and a small texture set hides it.
2. `python -m porter port <folder> --install`: the installer names the GPU and, for a game whose profile requires `bcn`, says that the textures are decoded on the CPU and how much memory that wants. It does not refuse.
3. Watch the first frames: the app's `log.txt` in its files folder (`adb pull /sdcard/Android/data/<package>/files/log.txt`). The report lines above come first, then the per-format lines as textures are met.
4. If a picture is wrong, the lines to look for, in the order they cost the least to rule out:
   - `[RED] zero-copy: fd N of M does not map` - no fd of a pool's handle maps, so that pool is copied at every submission: the 600 ms frame above. A gralloc difference to work around, not a driver bug.
   - `[RED] formats the replay needs that this GPU lacks` - a target or texture format the driver has no support for at all.
   - `[RED] a BC texture drawn into` - the game draws into a BC texture through a block-sized view (Mario Kart 8 Deluxe's reflection cubemaps); a decoded image cannot take those writes, and that pass needs its own handling.
   - `[RED] nvnBlendStateSetAdvancedMode N` - an advanced blend mode with no implementation: the state falls back to its blend functions, which draws something (the log names it once).
   - `[RED] a stage binds N samplers ... this GPU allows N` - a shader the device cannot bind (Bifrost-era Mali, not Valhall). That one shader's draws are skipped.
5. Measure: `DM_VK_PROF_SLOW=1` logs where a submission's replay time went (textures, pipelines, pool sync) when one passes 40 ms, `DM_VK_PROF=1` samples the replay thread's CPU time, and the `BC textures decoded` line gives the decode cost. If the decode dominates, `DM_VK_BC_MAX_MB` trades memory for it.

### Driving a game without hands

A development build (`--debug`) takes `DM_CTL=<file>` in `env.txt`: lines appended to that file are key presses, screenshots and pass dumps, acted on at once (`host/hle_hid.c`). `A`, `B`, `Left`, `LUp`, `A~0.5` (a hold), `shot /path.png`, `env DM_VK_SHOTS=4`. Look at a screen, decide, press, look again — no blind timed script, which is how the Blasphemous 2 menu was walked here.

### Without a Mali device

`DM_VK_X_BC_CPU=1` makes the host treat any GPU as one without BC: the whole decode path runs on an Adreno device. Put it in the profile's `android.tsv` (`env DM_VK_X_BC_CPU=1`) for a port that should always take it, or in the data pack's `env.txt` while testing. A picture that is wrong with the switch on is wrong on Mali too, and easier to bisect.

## Performance, measured (Blasphemous 2, Mali-G610 MC6)

Numbers from `DM_VK_PASS_TIMES=1` (per-pass GPU timestamps) and the front end's frame accounting, in the opening cinematic, docked (1920x1080) unless said otherwise:

| | |
|---|---|
| The frame's GPU time | 26 ms: 12.5 ms inside 43 passes and dispatches, **13.5 ms between them** (tile load/store, barriers, clears) |
| Handheld instead (1280x720 window) | 26-28 ms — **resolution is not the limit**: the game keeps 1920x1080 intermediates, and the cost is per pass, not per pixel |
| CPU, whole frame | p50 25-33 ms (`[perf] adaptive frame rate`) |
| GPU alone, 40 fps pinned | ~20 ms a frame, so the GPU could do about 50 fps |
| Switches that changed nothing (26-27 ms all) | `DM_VK_UBWC=0/1`, `DM_VK_ASYNC_PIPE=0`, `DM_VK_PASS_SPLIT=0`, `DM_VK_SETSPLIT=1`, `DM_VK_NOPREWARM=1` |
| `DM_VK_MT_REPLAY=1` | 22.9 ms GPU in one sample (noisy; not settled) |

What that says: the **CPU is the limiter** (frame work p50 ~29 ms against a 25 ms budget for 40 fps), the GPU sits at ~20 ms in this scene, and half of the GPU's time is spent *between* passes rather than drawing — which is what 43 passes of a tile-based GPU cost. `DM_FPS_PIN=40` holds 40 fps with about one frame in ten late; the governor's 30 fps is the smooth choice.

### What was optimized, and what it bought

`DM_VK_PROF=1` samples the process's CPU (1 ms, `ITIMER_PROF`) and prints the hottest library offsets; `llvm-addr2line` on the same build's `libdmhost.so` names them. In the main menu the top items were not the game:

| samples | where |
|---|---|
| 12% | `dm_thread_enter` (guest → host gate, `entry.S`) |
| 5.7% | `thread_state_char`, reading `/proc/self/task/<tid>/stat` on every preemption check (`hle_thread.c` `thr_running`) |
| 4.7% | `pool_copy_back`: a zero-copy pool finalized copies its whole 16 MB back, and the read out of the dma-buf is slow (MediaTek maps it uncached: ~160 ms a pool) |
| 3.1% | `img_new`, images made again after eviction |

Two changes came out of it:

1. **`thread_state_char` caches a thread's state for 1 ms** (`darwin_compat.c`). Menus went from 30 fps (frame work p50 29-33 ms) to **40 fps (p50 16.9 ms, no late frame in 64)** — the guest's preemption path was the frame's bottleneck there.
2. **`pool_copy_back` copies once instead of twice** (an anonymous region takes the bytes, `mremap` moves it onto the pool's address), halving the uncached read.

Gameplay is unchanged at 30 fps: in the cave the **GPU is 27 ms a frame** against 16.6 ms for 60, so the CPU win only shows where the CPU was the wall. Going further needs the GPU side — fewer passes or a smaller internal resolution, both per-game work.

Where a real gain would come from, in the order the numbers favour it:
1. **The replay's CPU cost** (the 29 ms): `DM_VK_MT_REPLAY` puts the replay on a thread of its own; per-game the porter's `--mt-replay` writes it into `env.txt`. Worth a proper A/B per game.
2. **Fewer passes**: the game's own post chain. Cutting one at 1920x1080 is ~1-2 ms of GPU; that is per-game work in the profile's `patches.py`, as the project already does for other titles.
3. **Texture bandwidth**: a BC texture decoded to RGBA8 is sampled at 4-8 times the console's bytes. Transcoded to ASTC 4x4 it would be 2x, but a CPU BC→ASTC encoder costs more than the bandwidth it saves; not attempted.

## What is not done

- **Intermittent garbage frames** (Blasphemous 2, the blessed-shrine cave): about one frame in 30-50 shows a band of the scene stretched into thin lines, or flat black and white slabs over it, and the next frame is clean. Reproduced by capturing the screen in a loop and diffing the scene area against a reference frame (`Pillow`); `async_pipe=0` gave 0 bad frames of 29 where `async_pipe=1` gave 1, which is too few to call it — a longer capture is needed, or a pass dump at the moment it happens. Two candidates: a vertex or index read that lands on garbage (NaN, or a buffer the GPU reads before the CPU's write reaches it) and the host's present reading the window image while it is still being written. `DM_CTL` `passdump 1` at that moment dumps the passes of the next frame; `DM_VK_ASYNC_PIPE=0` builds every pipeline at once instead of leaving a draw out until it is built.

- **The opening cinematic's video is black** (its subtitles and the surrounding UI draw): the game decodes H.264 through MediaCodec into the guest's NV12 buffer and converts it in a shader, so the fault is in that texture's path on Mali. One `[RED] nvnBlendStateSetAdvancedMode 25` appears during it, which is the first thing to look at.
- **A stage's descriptor limits.** Not hit on the G610 (500000 of each kind), but older Bifrost Mali reports 16 samplers and 16 sampled images a stage, where a game's shader that binds more cannot run at all; splitting a stage over more sets does not help, so that is per-game work.
- **Writes into BC textures.** Games that render into a BC texture through a view of its block size (Mario Kart 8 Deluxe, Splatoon-style reflection cubemaps) get a decoded colour image, so the block writes land as texels. Named in the log; not emulated.
- **`ReadTexels` of a BC texture** returns zeros when it is decoded on the CPU (it logs `[RED]`); rare, and nothing observed depends on it yet.
- **Mali driver bugs** of the kind Adreno needed (`gfx_vk_exec.c` has a dozen). Only one game has run so far.
- **The budget's default (2048 MB)** is a guess, not a measurement: it is what an 8 GB phone can give a game whose own pools take 2-4 GB.

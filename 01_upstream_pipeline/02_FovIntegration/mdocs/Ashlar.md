# FOV Integration 拼接流程

## 总体结构

FOV integration 分为三层：`batch_config.example.ini` 与 `generate_pipeline3.py` 负责选择步骤和串联线性 SLURM dependency；shell wrapper 负责项目路径、channel mapping、环境和参数适配；Python、MATLAB、Fiji macro 负责实际计算。

generator 的固定代码顺序为：

```text
11 -> 21 -> 12 -> 15 -> 22 -> 23 -> 24 -> 16 -> 27
```

它不推断 backend，也不构建动态 DAG。每个 `JOB_*` section 通过 `run_*` 只启用一条合法子序列：

```text
11 -> 12 -> 15 -> 23 -> 16 -> 27  # registration + Fiji
11 -> 12 -> 22 -> 23 -> 24 -> 27  # registration + Ashlar
21 -> 12 -> 15 -> 16 -> 27        # independent layout + Fiji
21 -> 12 -> 22 -> 24 -> 27        # independent layout + Ashlar
```

## TileConfiguration 文件契约

各步骤使用方法特异文件名，避免 downstream 把 Fiji 和 Ashlar 坐标混用：

```text
12_prepare_tile_config.sh
  -> TileConfiguration.initial.txt

15_fiji_estimate_coordinates.sh
  -> TileConfiguration.Fiji.txt

22_ashlar_stitch_initial.sh
  -> TileConfiguration.Ashlar.txt

23_prepare_moveImages_tileconfig.sh
  Fiji input   -> TileConfiguration.Fiji.<round>.txt
  Ashlar input -> TileConfiguration.Ashlar.<round>.txt
```

step 23 的 `--registered_config_name` 和 `--shifted_config_name` 都是必填参数。wrapper 不根据 backend 自动选择文件名；对应名称必须在 config 中显式成对设置。

## 步骤职责

- `11_nuclei_registration.sh`：按 SLURM array task 对 `Position*` 运行 MATLAB nuclei registration。
- `21_prepare_layout.sh`：把独立 round 的原始图像整理为 channel folders；Fiji 和 Ashlar 都可以消费这些目录。
- `12_prepare_tile_config.sh`：根据 Leica/Olympus metadata 生成 initial config，并运行 Fiji fusion-size preflight。
- `15_fiji_estimate_coordinates.sh`：用 Fiji registration/global optimization 估计坐标，发布 `TileConfiguration.Fiji.txt`。
- `22_ashlar_stitch_initial.sh`：用 Ashlar `EdgeAligner` 估计坐标，发布 `TileConfiguration.Ashlar.txt`。
- `23_prepare_moveImages_tileconfig.sh`：叠加 registration shift，整理 raw channel folders，写显式 shifted config。
- `24_ashlar_stitch_mosaic.sh`：不重新估计坐标，按指定 config 对 `CHANNEL_MODE` 对应通道做 Ashlar mosaic。
- `16_fiji_stitch_mosaic.sh`：不重新估计坐标，按指定 config 对 `CHANNEL_MODE` 或 `--channel_names` 对应通道做 Fiji mosaic。
- `27_make_rgbTIF_output.sh`：把显式 red/green stitched image 合成为 RGB OME-TIFF。

## Fiji fusion preflight

ImageJ1 的单个 XY plane 由 Java signed `int` 索引，像素数必须小于 `2^31 - 1 = 2147483647`。增加内存、平移坐标、改用 BigTIFF 或 `Write to disk` 都不能改变 fusion 创建单平面数组时的索引上限。

`p12_check_fiji_fusion_size.py` 从 initial config 读取 `(x, y)`，按 tile XY 尺寸计算：

```text
mosaic_width  = ceil(max_x + image_xy - min_x)
mosaic_height = ceil(max_y + image_xy - min_y)
pixel_count   = mosaic_width * mosaic_height
```

step 12 默认写 `fiji_fusion_preflight.json`。`fiji_fusion_safe=false` 是有效分析结果，step 12 仍成功，因此 Ashlar 路线不受阻塞。该报告用于人工判断是否运行 Fiji；step 15 不再读取报告或实施 gate，启动前应确认 `fiji_fusion_safe=true`。

该检查使用 initial coordinates，只负责提前识别明显超限布局，不保证 Fiji optimization 后的坐标不会进一步扩张。

## Fiji macro 契约

调用链保持为：

```text
shell export environment
  -> fiji_grid_collection_stitch.bsh: System.getenv()
  -> IJ.runMacroFile(..., key=value;...)
  -> fiji_grid_collection_stitch.ijm: getArgument()
```

`Positions_from_file_mosaic` 是 step 16 的默认坐标复用分支。该分支只使用 `layout_file`、`fusion_method`、`subpixel_accuracy` 和 `image_output=[Fuse and display]`，不包含 `compute_overlap`、registration thresholds 或 `computation_parameters`。`Positions_from_file_p1`、`Positions_from_file_p2` 和 downsampled 分支保留为备用路径，但 step 16 默认不调用。

所有 active Fiji fusion 分支在 fusion 后无条件执行 Max Intensity Z projection，只保存当前 2D projection。默认格式为普通 TIFF；`ome_tiff` 和 `ome_bigtiff` 通过 Bio-Formats Exporter 显式输出，不能只靠改扩展名伪装 OME 文件。Fiji 路线保持 `Fuse and display`，不使用 `Write to disk`。

## Channel selection

step 16 和 step 24 都只处理解析后的 channel list，不扫描 work directory 下的任意子目录。支持：

```text
LeicaIF
OlympusIF
LeicaSeqE
LeicaIFIndependent
OlympusIFIndependent
LeicaSeqEIndependent
```

step 16 的非空 `--channel_names` 会覆盖 `--channel_mode` 映射。每个 channel 只执行一次 mosaic，并把 work-dir config 复制为 channel-local `TileConfiguration.mosaic.txt` 后交给 Fiji。

## Config namespace

```text
prepare_layout_*          # step 21
prepare_tile_config_*     # step 12
fiji_stitch_*             # step 15
ashlar_stitch_*           # step 22
prepare_shifted_layout_*  # step 23
ashlar_mosaic_*           # step 24
fiji_mosaic_*             # step 16
rgb_tif_*                 # step 27
```

所有现役 wrapper 使用具名参数，并接受 `--script_dir` 覆盖。wrapper 的默认 `SCRIPT_DIR` 是当前部署目录的明确绝对路径，Python callee 从最终 `SCRIPT_DIR` 派生。

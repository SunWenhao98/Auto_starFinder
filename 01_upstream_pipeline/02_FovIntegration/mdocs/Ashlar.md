# FOV Integration 拼接流程

## 总体结构

`batch_config.upstream.ini` 与 `generator_upstream_pipeline.py` 选择步骤并串联 SLURM dependency。shell wrapper 解析样本路径、轮次和 panel，Python、MATLAB 与 Fiji macro 完成实际处理。

generator 按固定顺序为每个 `JOB_*` 中启用的步骤串联 `afterok`。常见入口如下。

```text
11a -> 11b -> 12 -> 15 -> 23 -> 16  # 逐 FOV 位移与 Fiji 拼接
11a -> 11b -> 12 -> 22 -> 23 -> 24  # 逐 FOV 位移与 Ashlar 拼接
11b -> 12 -> 15/22                  # 参考轮或独立轮精配
11b -> 12 -> 31 -> 32               # 三轮联合坐标与共画布出图
```

`11a` 的位移和 `11b → 12 → 15/22` 的参考精配坐标在 `23` 汇合。IF 与 seqE 分别选择自己的位移日志和 moving 输出坐标表。

## 步骤职责

| 步骤 | 输入与职责 | 主要输出 |
|---|---|---|
| `11a_nuclei_registration.sh` | 同一个 FOV 的参考轮与 moving 轮 DAPI，沿用 DFT 算法估计平移 | `PositionXXX/log/log_protein_registration_<tag>.txt` |
| `11b_prepare_layout.sh` | 按轮次和 panel 准备通道布局 | `PositionXXX.tif` 文件软链接及来源清单 |
| `12_prepare_tile_config.sh` | 参考图列表与 Leica/Olympus metadata | `TileConfiguration.initial.txt`、`tile_summary.csv` 和 fusion-size preflight |
| `15_fiji_stitch_initial.sh` | 参考 DAPI 与 initial config，运行 Fiji registration/global optimization | 配置指定的 Fiji 精配坐标与参考拼图 |
| `22_ashlar_stitch_initial.sh` | 参考 DAPI 与 initial config，运行 Ashlar `EdgeAligner` | 配置指定的 Ashlar 精配坐标与参考拼图 |
| `23_prepare_moveImages_tileconfig.sh` | 参考精配坐标与选定的逐 FOV 位移日志 | moving 坐标表及同 stem 的 `.shifts.csv` |
| `16_fiji_stitch_mosaic.sh`、`24_ashlar_stitch_mosaic.sh` | 读取 `11b` 的通道布局，按指定坐标融合 | 各通道拼图 |
| `31_ashlar_stitch_joint.sh`、`32_ashlar_stitch_mosaic_joint.sh` | 联合求解三轮坐标并按共画布导出 | ref、IF、seqE 的坐标和拼图 |
| `33_prepare_mosaic_display.sh` | 读取已经同网格的 MIP 或 Z 平面 | 多通道 OME-TIFF、叠加 PNG 和展示预设 |

新提交脚本使用 `11a/11b` 入口。旧脚本执行前应按当前完整 INI 重新生成。

## 11a 的图像开关

`nuclei_reg_apply_and_save_images = false` 为默认配置，对应 wrapper 的 `--apply_and_save_images`。每个 FOV 仅读参考 DAPI 与 moving DAPI，记录 `Shifted by`。位移日志沿用 `[rowShift, colShift, zShift]`，单位为像素。

设为 `true` 时，读取 moving 各通道，应用同一组位移，按原通道顺序和输出命名写出完整图像及 `ref-DAPI`。这些对齐图像使用自己的实体输出目录。`11b` 的原图链接布局供拼接读取。

`nuclei_reg_aligned_round_outdir` 决定位移日志的 tag。IF 与 seqE 使用各自的 tag，`prepare_moveimages_registration_log_name` 显式选择完整日志文件名，例如 `log_protein_registration_IF_ref001.txt`。日志位于各 `PositionXXX/log/` 下。目录名含路径分隔符时，wrapper 与 MATLAB 使用相同的 tag 清洗规则。

## 11b 的轮次布局

单轮配置使用 `prepare_layout_rawdata_round`、`prepare_layout_channel_mode` 和 `prepare_layout_stitching_workdir`。其中 `LeicaRef` 仅准备 `ch03=raw-refDAPI`，`LeicaIF/OlympusIF` 准备四个 IF 通道，`LeicaSeqE` 准备四个 seqE 通道。

三轮配置通过 `prepare_layout_round_manifest` 提供 CSV 的完整路径，对应 `--round_manifest`。generator 原样转发路径，wrapper 按清单解析样本内的原始轮次和输出子目录。清单示例如下。

```csv
role,rawdata_round,channel_mode,subdir
ref,round001,LeicaRef,ref
IF,IF,LeicaIF,IF
seqE,round011,LeicaSeqE,seqE
```

清单可在同一批样本间复用。不同参考轮使用相应清单，例如参考 `round005` 时将 ref 行的 `rawdata_round` 设为 `round005`。每轮保留自己的 FOV 覆盖，配准比较采用已确定的共同范围。

同一方法根下的布局如下。

```text
<method>/
  ref/raw-refDAPI/PositionXXX.tif
  IF/raw-561-CA9/PositionXXX.tif
  IF/raw-488-CD144/PositionXXX.tif
  IF/raw-647-CD31/PositionXXX.tif
  IF/raw-DAPI/PositionXXX.tif
  seqE/raw-647-GCnt/PositionXXX.tif
  seqE/raw-561-GTrb/PositionXXX.tif
  seqE/raw-Padlayer/PositionXXX.tif
  seqE/raw-DAPI/PositionXXX.tif
```

`prepare_layout_mode = symlink` 与 `prepare_layout_output_format = preserve` 为默认组合。各方法、轮次和通道目录都是独立实体目录，目录中的 TIFF 逐文件链接到源文件。Fiji 会在输入通道目录写入坐标配置和整幅拼图，各方法因此需要独立的目录。

链接时解析源 TIFF 的实体路径，避免目标经过仅属主可遍历的 home 别名。来源清单记录实际源文件和布局文件。相同位置、相同源的既有链接可复用，断链、不同源链接或同名实体文件作为冲突报告。链接沿用目标已有的读取权限，计算节点和实际执行账号需要能够遍历源目录并读取 TIFF。

需要位深转换时，显式使用 `prepare_layout_mode = copy` 和所需 `prepare_layout_output_format`。原始位深参考图与旧 `11` 输出的 8 位参考图在量化上可能有差异，初始精配坐标需按本次输入口径验收。

## 三轮布局的调用配置

完整 INI 的单轮默认值只准备参考 DAPI。一次准备三轮时，填写上面的 CSV，并让各步骤使用同一方法根。下面是 A Fiji 的关联配置片段，合并到完整 INI 后由 generator 生成提交脚本。

```ini
nuclei_reg_aligned_round_outdir = IF_ref001
prepare_layout_stitching_workdir = A_Fiji
prepare_layout_round_manifest = /absolute/path/round_layout.csv
prepare_tile_config_stitching_workdir = A_Fiji
prepare_tile_config_source_channel_dir = ref/raw-refDAPI
fiji_stitch_initial_stitching_workdir = A_Fiji
fiji_stitch_initial_source_channel = ref/raw-refDAPI
prepare_moveimages_stitching_workdir = A_Fiji
prepare_moveimages_registration_log_name = log_protein_registration_IF_ref001.txt
fiji_stitch_mosaic_stitching_workdir = A_Fiji
fiji_stitch_mosaic_channel_dir_prefix = IF/raw-
```

seqE 的 11a/23 调用使用自己的 moving_round、日志 tag、输出坐标表名，16/24 的通道前缀使用 `seqE/raw-`。单个 JOB 中 generator 每个步骤执行一次，两个 moving 轮分别配置 JOB 或明确调用，11b 的三轮布局清单可以共用。

Ashlar 的对应参数为 `ashlar_stitch_initial_source_channel_dir` 和 `ashlar_stitch_mosaic_channel_dir_prefix`。31/32 使用 `ref/raw-refDAPI`、`IF/raw-`、`seqE/raw-` 的同一布局。

## 已知的少层 TIFF 读取限制

现有 Ashlar reader 对 3 页灰度 TIFF 存在轴解释问题。验收中，skimage 将实体源文件和它的文件链接都读为 YXC，当前 22/24 的 ZYX 假设会得到错误画布。tifffile 能保留其 ZYX 结构。该问题属于既有 reader 行为，需另行修订 reader。

本轮真实 Fiji/Ashlar 链的通过范围为 5 层合成输入。真实源链接读取检查使用 45 层图像。11a 的单层与 5 层 MATLAB 契约均已通过。

## TileConfiguration 与 23 的契约

单轮参考布局的 source channel 为 `raw-refDAPI`，三轮清单布局为 `ref/raw-refDAPI`。`12`、`15/22` 应读取同一套参考图，并使用显式配置的坐标表名。

`23` 通过 `--input_config`、`--output_config` 和 `--registration_log_name` 选择输入坐标、输出坐标和位移日志。默认 `shift_sign=1`、`rotate_shifts=false` 时，输出为 `X += colShift`、`Y += rowShift`、`Z += zShift`。每个条目按真实 `PositionXXX` 对应日志。

输出坐标表的 stem 决定 shifts 表名，例如 `TileConfiguration.IF.moving.Fiji.txt` 对应 `TileConfiguration.IF.moving.Fiji.shifts.csv`。IF 和 seqE 使用不同的输出坐标表名，在同一方法根下分别保存。shifts 表的 `moving_x/moving_y/moving_z` 表示当前 moving 轮更新后的放置坐标。

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
nuclei_reg_*              # 11a
prepare_layout_*          # 11b
prepare_tile_config_*     # 12
fiji_stitch_initial_*     # 15
ashlar_stitch_initial_*   # 22
prepare_moveimages_*      # 23
fiji_stitch_mosaic_*      # 16
ashlar_stitch_mosaic_*    # 24
ashlar_joint_stitch_*     # 31
ashlar_joint_mosaic_*     # 32
mosaic_display_*          # 33
```

wrapper 通过显式 `--script_dir` 或 `--core_matlab_dir` 定位 runner，运行前打印实际输入、输出和环境。配置及提交日志存放在项目工作区，业务图像与坐标存放在样本 registration root。

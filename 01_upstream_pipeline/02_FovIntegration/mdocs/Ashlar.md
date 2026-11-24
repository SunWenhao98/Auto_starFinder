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

正式五方法目录如下；A/B/C 仅用于说明执行路线。

| 方法目录 | 路线 | 处理方式 |
|---|---|---|
| `21_reg_stitch_Fiji` | A | 逐FOV配准后，按参考轮Fiji坐标融合 |
| `22_reg_stitch_Ashlar` | A | 逐FOV配准后，按参考轮Ashlar坐标融合 |
| `23_stitch_reg_Fiji` | B | 各轮Fiji独立拼接后，估计轮间变换并跨通道复用 |
| `24_stitch_reg_Ashlar` | B | 各轮Ashlar独立拼接后，估计轮间变换并跨通道复用 |
| `25_joint_stitch_Ashlar` | C | Ashlar联合求解后导出各轮拼图 |

GBM006–009 的 A 路线 IF 为 N/A：同号FOV已无法对应配准；这些样本的参考轮与seqE仍按各自适用步骤处理。B/C不因这一限制跳过IF。

各方法目录放在样本已有registration根内：GBM001–009、GBM017–026使用 `02_registration001_<sample>`，GBM010–016使用 `02_registration001_<sample>_ref1`；GBM015的round005分支使用 `02_registration002_GBM015_ref5`。INI的 `regDir_suffix` 显式选择该根，不由方法名推断。后续新运行写入这些根内的新方法目录，不移动或覆盖旧方法结果。

## 步骤职责

| 步骤 | 输入与职责 | 主要输出 |
|---|---|---|
| `11a_nuclei_registration.sh` | 同一个 FOV 的参考轮与 moving 轮 DAPI，沿用 DFT 算法估计平移 | `PositionXXX/log/log_protein_registration_ref-<round>_moving-<round>.txt` |
| `11b_prepare_layout.sh` | 按轮次和 panel 准备通道布局 | `PositionXXX.tif` 文件软链接及来源清单 |
| `12_prepare_tile_config.sh` | 每个样本、方法读取一次参考图列表与 Leica/Olympus metadata | 方法根的 `TileConfiguration.initial.txt`、`tile_summary.csv`、布局图和 fusion-size preflight；各轮的初始文件链接 |
| `15_fiji_stitch_initial.sh` | 参考 DAPI 与 initial config，运行 Fiji registration/global optimization | 配置指定的 Fiji 精配坐标与参考拼图 |
| `22_ashlar_stitch_initial.sh` | 参考 DAPI 与 initial config，运行 Ashlar `EdgeAligner` | 配置指定的 Ashlar 精配坐标与参考拼图 |
| `23_prepare_moveImages_tileconfig.sh` | 参考精配坐标与选定的逐 FOV 位移日志 | moving 坐标表及同 stem 的 `.shifts.csv` |
| `16_fiji_stitch_mosaic.sh`、`24_ashlar_stitch_mosaic.sh` | 读取 `11b` 的通道布局，按指定坐标融合 | 各通道拼图 |
| `31_ashlar_stitch_joint.sh`、`32_ashlar_stitch_mosaic_joint.sh` | 联合求解三轮坐标并按共画布导出 | ref、IF、seqE 的坐标和拼图 |
| `33_prepare_mosaic_display.sh` | 每轮读取已经同网格的二维 MIP 通道 | 多通道 OME-TIFF、叠加 PNG 和展示预设 |

新提交脚本使用 `11a/11b` 入口。旧脚本执行前应按当前完整 INI 重新生成。

## 11a 的图像开关

`nuclei_reg_apply_and_save_images = false` 为默认配置，对应 wrapper 的 `--apply_and_save_images`。每个 FOV 仅读参考 DAPI 与 moving DAPI，记录 `Shifted by`。位移日志沿用 `[rowShift, colShift, zShift]`，单位为像素。

两轮分别通过 `nuclei_reg_ref_input_format` 和 `nuclei_reg_moving_input_format` 指定实际TIFF存储类型，对应 `--ref_input_format` 和 `--moving_input_format`。正式模板中参考轮为uint16、IF为uint8；seqE的moving类型显式设为uint16。`nuclei_reg_norm_out_format=uint16` 是工作图像类型，可容纳上述两种输入的原始像素值，不把uint8输入的0–255范围拉伸为0–65535；旧的单一 `nuclei_reg_input_format` 不再使用。

设为 `true` 时，读取 moving 各通道，应用同一组位移，按原通道顺序和输出命名写出完整图像及 `ref-DAPI`。这些对齐图像使用自己的实体输出目录。`11b` 的原图链接布局供拼接读取。

`nuclei_reg_aligned_round_outdir` 仅在显式开启图像保存时命名对齐图像目录。规范位移日志按实际轮次对命名，例如 `log_protein_registration_ref-round001_moving-IF.txt` 和 `log_protein_registration_ref-round001_moving-round011.txt`，位于各 `PositionXXX/log/` 下，并记录实际读取的两轮DAPI路径。成功完成后更新同一轮次对的规范日志，其他旧命名历史日志保留。`prepare_moveimages_registration_log_name` 显式选择23需要读取的完整文件名；参考轮为round005时，两处日志名称均使用 `ref-round005`。

## 11b 的轮次布局

单轮配置使用 `prepare_layout_rawdata_round`、`prepare_layout_channel_mode` 和 `prepare_layout_stitching_workdir`。其中 `LeicaRef` 仅准备 `ch03=raw-refDAPI`，`LeicaIF/OlympusIF` 准备四个 IF 通道，`LeicaSeqE` 仅准备 ch00=647-GCnt、ch01=561-GTrb、ch03=DAPI 三个真实通道。原始 ch02=Padlayer 继续供解码占位，11a 的四项 panel 保留；拼接层不链接或融合该空白通道。

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
  TileConfiguration.initial.txt
  tile_summary.csv
  fiji_fusion_preflight.json
  ref/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  ref/tile_summary.csv -> ../tile_summary.csv
  ref/raw-refDAPI/PositionXXX.tif
  IF/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  IF/tile_summary.csv -> ../tile_summary.csv
  IF/raw-561-CA9/PositionXXX.tif
  IF/raw-488-CD144/PositionXXX.tif
  IF/raw-647-CD31/PositionXXX.tif
  IF/raw-DAPI/PositionXXX.tif
  seqE/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  seqE/tile_summary.csv -> ../tile_summary.csv
  seqE/raw-647-GCnt/PositionXXX.tif
  seqE/raw-561-GTrb/PositionXXX.tif
  seqE/raw-DAPI/PositionXXX.tif
```

`prepare_layout_mode = symlink` 与 `prepare_layout_output_format = preserve` 为默认组合。各方法、轮次和通道目录都是独立实体目录，目录中的 TIFF 逐文件链接到源文件。Fiji 会在输入通道目录写入坐标配置和整幅拼图，各方法因此需要独立的目录。

`12` 在方法根运行一次，复用同一份 `prepare_layout_round_manifest` 建立上述初始配置和summary链接；链接在初始文件成功生成后创建，不另提交建链作业。共享前核对各轮Position覆盖与根initial实际映射一致；不一致时停止，不能静默丢弃额外或缺失FOV。各方法独立生成自己的initial，不跨方法复制或链接。下文约束后续新运行，不回写已完成结果或历史提交脚本。

只有initial和名义summary共用；“只读”指下游仅将它们作为读取输入，不通过链接写入，不改变文件权限或ACL。Fiji通道目录中的 `TileConfiguration.txt` 是工作副本，registered、moving与各轮诊断是独立输出，不能链接回共享initial。`tile_summary.csv` 在各轮保留入口供后续reads整合使用；布局图和preflight只需在方法根保存一份。initial、summary和布局图采用独占写入；新运行使用新的方法工作目录。

链接时解析源 TIFF 的实体路径，避免目标经过仅属主可遍历的 home 别名。来源清单记录实际源文件和布局文件。相同位置、相同源的既有链接可复用，断链、不同源链接或同名实体文件作为冲突报告。链接沿用目标已有的读取权限，计算节点和实际执行账号需要能够遍历源目录并读取 TIFF。

需要位深转换时，显式使用 `prepare_layout_mode = copy` 和所需 `prepare_layout_output_format`。原始位深参考图与旧 `11` 输出的 8 位参考图在量化上可能有差异，初始精配坐标需按本次输入口径验收。

## 三轮布局的调用配置

完整INI默认关闭各步骤；启用三轮布局前，填写上面的CSV，并让各步骤使用同一方法根。单轮直接调用时，须显式匹配11b的输出位置和12的source路径。下面是A Fiji的关联配置片段，合并到完整INI后由generator生成提交脚本。

```ini
nuclei_reg_ref_input_format = uint16
nuclei_reg_moving_input_format = uint8
nuclei_reg_norm_out_format = uint16
nuclei_reg_moving_round = IF
nuclei_reg_apply_and_save_images = false
prepare_layout_stitching_workdir = 21_reg_stitch_Fiji
prepare_layout_round_manifest = /absolute/path/round_layout.csv
prepare_tile_config_stitching_workdir = %(prepare_layout_stitching_workdir)s
prepare_tile_config_source_channel_dir = ref/raw-refDAPI
prepare_tile_config_output_config = TileConfiguration.initial.txt
fiji_stitch_initial_stitching_workdir = %(prepare_layout_stitching_workdir)s/ref
fiji_stitch_initial_source_channel = raw-refDAPI
fiji_stitch_initial_input_config = TileConfiguration.initial.txt
fiji_stitch_initial_output_config = TileConfiguration.registered.round001.Fiji.txt
prepare_moveimages_stitching_workdir = %(prepare_layout_stitching_workdir)s
prepare_moveimages_registration_log_name = log_protein_registration_ref-round001_moving-IF.txt
prepare_moveimages_input_config = ref/TileConfiguration.registered.round001.Fiji.txt
prepare_moveimages_output_config = IF/TileConfiguration.moving.IF.Fiji.txt
fiji_stitch_mosaic_stitching_workdir = %(prepare_layout_stitching_workdir)s/IF
fiji_stitch_mosaic_input_config = TileConfiguration.moving.IF.Fiji.txt
fiji_stitch_mosaic_channel_dir_prefix = raw-
```

seqE 的11a调用设 `nuclei_reg_moving_round=round011`、`nuclei_reg_moving_input_format=uint16`、`nuclei_reg_channel_panel=LeicaSeqE`；23读取 `log_protein_registration_ref-round001_moving-round011.txt`，输出设为 `seqE/TileConfiguration.moving.round011.Fiji.txt`。16的workdir为 `21_reg_stitch_Fiji/seqE`，读取该文件名，通道前缀仍为 `raw-`。单个JOB中generator每步骤执行一次，moving轮可分别配置JOB或明确调用；只有方法级准备JOB启用12，其余各轮任务复用链接，不再次启用12。现有编排须让各轮初始精配等待这一次12成功。

Ashlar使用自己的方法根和相同布局约定；参考精配输出例如 `ref/TileConfiguration.registered.round001.Ashlar.txt`，moving输出例如 `IF/TileConfiguration.moving.IF.Ashlar.txt`。B路线各轮15/22仍分别精配，只共享MAF初始坐标；C路线由31联合求解。31/32在方法根使用 `ref/raw-refDAPI`、`IF/raw-`、`seqE/raw-`。实际参考轮为round005时，所有reference坐标文件名和消费者同步改为round005，不能只写ref而省略轮次。

后续reads整合应明确选择该后端的参考精配文件：Fiji模板默认跟随 `fiji_stitch_initial_output_config`，Ashlar方法需将 `cellreads_registered_tile_config` 设为 `%(ashlar_stitch_initial_output_config)s`，对应目录仍为该方法的 `ref`。联合拼接则选择方法根及其带实际参考轮名的AshlarJoint输出。

## 同轮 MIP 展示

本批 IF 四通道、seqE 三通道分别调用 33，使用各自的输入清单、profile 和新输出目录，例如 `display_review/IF`、`display_review/seqE`。每次输出二维多通道 `mip.ome.tif`、RGB 叠加 PNG 与 `display_presets.json`；OME 的 C 轴是通道，不是完整 Z 堆栈。generator 每个 JOB 调用 33 一次，两轮使用两个 JOB。

33的 `mosaic_display_input_manifest`、`mosaic_display_profile` 接受绝对路径，也保留相对方法工作目录的路径。批次清单和profile保存在工作目录，图像仍留在各方法的数据目录；外置清单内的图像路径宜显式写绝对路径，若写相对路径则以清单自身父目录为基准。29的通道清单同样接受绝对路径，原有相对registration根的路径仍有效；清单内相对通道路径也以通道清单JSON自身的父目录为基准。

同轮通道必须使用同一套拼接坐标、像素网格和方向。A 路线保留各轮自然画布，不增加强制跨轮统一；B/C 已有画布行为保留。Z 位移日志沿用，不新增指定层补偿。本批配置 `make_3d=false`、`slice_indices=`，以 MIP 为展示交付。一般工具的指定二维层接口保留，但不是本批必需产物。

## 灰度 TIFF 的读取约定

22、24、30 的首图尺寸识别与实际读图统一使用 `tifffile.imread()`；31 复用 30 的 reader，32 原本已使用同一 TIFF API。输入沿用逐通道文件约定：二维数组为 `Y,X`，多页灰度堆栈为 `Z,Y,X`。普通多页 TIFF 的元数据也可能标为 `QYX`，不能要求轴标签必须等于 `ZYX`。

读取本身保留原位深，24/32 仍按显式 `output_format` 执行既有位深转换。MIP 沿第 0 轴投影，`slice_index` 按 1-based Z 层选择，stack 的 `read(series, c)` 中 c 为 0-based Z 索引，对应第 c+1 层；取出二维平面后再按既有设置旋转。这里修正读取方式，坐标单位、原点换算、配准算法及 CLI 均保持原样。

旧 `skimage.io.imread()` 会将某些 3/4 页堆栈自动换成通道在末尾的数组，导致错误的 tile 尺寸、投影、画布，也可能影响配准坐标。文件软链接与实体文件均会触发该旧行为。当前直接读取 TIFF，不再经过这一换轴步骤。

回归入口为 `test_contracts/test_ashlar_tiff_readers.py` 与 `test_contracts/test_joint_three_round_contracts.py`。前者使用非正方形小图覆盖二维、3/4/5/45 层、uint8/uint16、MIP/指定层/stack 像素及顺时针旋转；后者保留二维测试并增加三轮 3 页真实 TIFF/CLI 的坐标、共同画布及地标叠加检查。reader 的 stack 逐层读取检查不等于导出 OME-TIFF 的 C/Z 元数据验收。

前轮 11a/11b 布局验收的 Fiji/Ashlar 完整链通过范围为 5 层合成输入，真实源链接读取检查为 45 层；这些历史记录保留原范围。本次少层 reader 修复另用全新测试目录验收，不覆盖旧拼图或坐标。

## TileConfiguration 与 23 的契约

单轮参考布局的source channel为 `raw-refDAPI`。三轮布局中12的workdir是方法根、source channel为 `ref/raw-refDAPI`；15/22的workdir是方法根下的 `ref`、source channel为 `raw-refDAPI`，因此两者读取同一套参考图。15/22读取各轮目录中的initial链接，22的诊断也留在各轮目录，不把多个轮次的输入路径直接改为方法根。

`23` 通过 `--input_config`、`--output_config` 和 `--registration_log_name` 选择输入坐标、输出坐标和位移日志。默认 `shift_sign=1`、`rotate_shifts=false` 时，输出为 `X += colShift`、`Y += rowShift`、`Z += zShift`。每个条目按真实 `PositionXXX` 对应日志。

输出坐标表的stem决定shifts表名，例如 `IF/TileConfiguration.moving.IF.Fiji.txt` 对应 `IF/TileConfiguration.moving.IF.Fiji.shifts.csv`；seqE示例为 `seqE/TileConfiguration.moving.round011.Fiji.txt`。registered和moving名称同时标明实际轮次与后端。shifts表的 `moving_x/moving_y/moving_z` 表示当前moving轮更新后的放置坐标，A路线最终融合继续读取23产出的moving配置，不用共同initial替代位移后的坐标。

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

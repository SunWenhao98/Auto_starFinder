# 31–32: Joint ref / IF / seqE Stitching

本流程用各轮 DAPI 联合求解 FOV 位置，再把位置与轮次变换用于该轮全部通道。ref、IF、seqE 保留各自的 FOV 清单，最终输出同一原点、尺寸与方向的画布，可直接叠加。

`30` 是可单独使用的单轮 MST/LSQ 拼接；`31` 复用其求解器，但不要求先执行 `30`。`32` 只按已求出的几何关系出图，不重新配准蛋白或 seqE 信号。

## 输入与准备

三轮需要各自的DAPI tile目录和对应的名义TileConfiguration。31求解器本身保留独立FOV/config输入能力，不要求三轮同名、同数量，也不先取交集。标准共享准备仍按11b→12执行：11b布局各轮全部原始FOV，12按参考轮生成方法根initial，并在建立链接时核对各轮均包含其中要求的Position；缺少必需FOV时停止，额外moving FOV允许且保留布局。读取器按config选图，额外FOV不会自动进入共享config的求解；如需纳入，显式提供该轮独立config。MAF的物理Position身份与样本offset在准备时核对，不能用过滤后的细胞矩阵清单替代原始拍摄清单。

推荐在新的stitching workdir内使用以下实体子目录；11b准备通道布局，12生成初始配置及其链接，31/32读取这些输入：

```text
new_joint_workdir/
  TileConfiguration.initial.txt    # 本方法运行一次12的名义坐标
  tile_summary.csv
  ref/raw-refDAPI/                  # 参考轮 ch03
  ref/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  ref/tile_summary.csv -> ../tile_summary.csv
  IF/raw-DAPI/                     # IF ch03
  IF/raw-561-CA9/                   # IF ch00
  IF/raw-488-CD144/                 # IF ch01
  IF/raw-647-CD31/                  # IF ch02
  IF/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  IF/tile_summary.csv -> ../tile_summary.csv
  seqE/raw-DAPI/                   # round011 ch03
  seqE/raw-647-GCnt/                # round011 ch00
  seqE/raw-561-GTrb/                # round011 ch01
  seqE/TileConfiguration.initial.txt -> ../TileConfiguration.initial.txt
  seqE/tile_summary.csv -> ../tile_summary.csv
```

`11b`的IF和seqE模式都会生成 `raw-DAPI`，因此两轮使用独立子目录。三轮布局通过11b的轮次清单准备；12读取参考DAPI、在本方法根计算一次名义坐标，复用同一清单在成功后创建各轮相对链接。其它方法独立运行自己的12，不跨方法共享；其它轮次任务不重复启用12。名义summary与布局图、preflight也只计算一次。保留原始位深时，准备与出图都选择 `preserve`；已转为uint8的输入无法通过后续转回uint16恢复精度。

每通道 TIFF 按二维 `Y,X` 或灰度堆栈 `Z,Y,X` 读取。31 通过 30 的 reader 使用 `tifffile.imread()`，32 同样直接读取 TIFF，3/4 页堆栈不会再经过 skimage 的自动换轴。普通多页 TIFF 的 `QYX` 元数据沿用本流程的 Z 页堆栈语义；配准使用 MIP，指定层与 stack 按 Z 选择。

## 实际调用链与算法

```text
各轮布局和名义 config → 31 wrapper → p31 → p30.MSTEdgeAligner
                                         ↓
                          三份联合 config + summary
                                         ↓
                       32 wrapper → p32 → 八个单通道 MIP mosaic
```

1. **读入与节点对应**：每轮分别读取 MIP，按 ref、IF、seqE 连接节点索引。轮内文件名必须唯一；不同轮允许出现同名 FOV。当前 Ashlar 配准使用一个共享 tile XY 尺寸，因此不同轮尺寸不同时明确失败。
2. **粗定位**：三轮名义坐标放在同一低分辨率画布，缩小 16 倍；按各轮实际覆盖范围建立 mask，使用 masked normalized cross-correlation 得到 IF、seqE 相对 ref 的粗平移；平滑在有效覆盖边界按权重归一化，避免把缺失 FOV 当成暗信号。此处沿用 scikit-image 0.26 的默认最小重叠比例 0.3。粗平移用于发现实际重叠的邻居，不要求同编号 FOV 之间有重叠。
3. **一次联合问题**：以矩形真实交叠建立候选边，包含位置完全重合的跨轮 tile。ref–ref、IF–IF、seqE–seqE 和各跨轮边共同进入 MST、一致性/环路复核及加权 LSQ。三轮并非两次独立的 ref–moving 求解。
4. **分别估计几何变换**：从第一遍各轮内部边求得未旋转布局，固定这些布局；利用 ref 与每个 moving 的实测跨轮边拟合相似变换。IF、seqE 分别估计旋转和尺度。默认旋转阈值 10 mdeg，超过阈值时绕 tile 中心按拟合的相似变换重采样；所有轮随后再次联合求解。最多三次重采样复求解，变化小于 1 mdeg 时停止，summary 记录收敛状态。小于旋转阈值时不会单独因尺度差异而重采样。
5. **有效连接与输出**：相似变换必须有可辨识的实测边；最终每个 moving 连通分量必须通过实测跨轮边到达 ref，不能仅靠猜测跨轮边判为成功。轮内低纹理 tile 可沿用名义布局 fallback，需结合边表人工复核。最终配置保留 0.01 px 精度，全部输出坐标的外包范围确定共同画布。

当前不是非刚性配准，也不保证任意大旋转、弱 DAPI 或完全无重叠样本可成功。每个 moving 的相似变换仍需与 ref 的有效直接匹配。三轮联合会影响 ref 的最终位置，和旧双轮结果不是同一个可直接互换的坐标版本。

## 共同画布与输出

每轮都使用以下关系，不再按各轮 config 分别归零：

```text
canvas_pixel_yx = joint_coordinate_yx - canvas_origin_yx
canvas_shape_yx = ceil(max(all_tile_positions + tile_size) - canvas_origin_yx)
```

`p32` 从新 summary 读取共同原点、尺寸、`rotate90` 与 `rounds[round_name].tile_transform`。先按记录的方向旋转 tile，再应用该轮变换，最后放入共同画布。MIP、指定 Z 切片和既有 stack 分支均沿用这个 XY 画布。缺少某轮覆盖的位置为空白，不裁掉该轮以外的视野。

| 输出 | 含义 |
|---|---|
| `TileConfiguration.registered.round001.AshlarJoint.txt` | ref 全部 FOV 的联合坐标 |
| `TileConfiguration.registered.IF.AshlarJoint.txt` | IF 全部 FOV 的联合坐标 |
| `TileConfiguration.registered.round011.AshlarJoint.txt` | seqE 全部 FOV 的联合坐标，启用 seqE 时生成 |
| `<prefix>_summary.json` | 各轮输入、配置、变换、收敛状态、共同画布与边组残差 |
| `<prefix>_coordinates.csv`、`_<round>_coordinates.csv` | 联合及各轮位置；行键是 round + filename |
| `<prefix>_if_fov_shifts.csv`、`_seqe_fov_shifts.csv` | 同名 ref 对照及各自名义位置的偏移；无同名 ref 时 `has_matching_ref=false`、对应参考坐标为空，不删除该 FOV |
| `<prefix>_edge_alignment.csv`、可选 `_pass1_edge_alignment.csv` | 最终及首遍实测边、筛选状态与 LSQ 残差 |

同名 FOV 偏移表是位置诊断，经过旋转的图像需要同时应用 tile transform，不能把该表当作旧逐 FOV 纯平移流程的直接替代。

32 输出参考 DAPI 一通道、IF 四通道、seqE 三通道，共八通道。前缀分别为 `<prefix>_refDAPI`、`<prefix>_<IF channel>`、`<prefix>_seqE_<seqE channel>`；IF DAPI 与 seqE DAPI 不会撞名。seqE 的拼接通道固定为 647-GCnt、561-GTrb、DAPI；原始 ch02=Padlayer 与 11a 四项 panel 保留，拼接不处理占位通道。

本批正式图像使用 `*_2d.ome.tif` MIP 金字塔图，`make_3d=false`、`slice_indices=`。33 分别打包 IF 四通道和 seqE 三通道 MIP，输出二维多通道 OME-TIFF 和叠加 PNG。已有 C 路线三轮共画布能力保留，但展示只要求各轮内部通道匹配；不增加完整 3D 叠加或 Z 位移补偿验收。

写入前检查本次目标路径，已有结果直接失败；不提供覆盖开关。输入与输出可同属 workdir，重复计算应换新的工作目录或完整输出名，不能删除旧文件后冒充续跑。

## 三轮配置示例

以下为完整批配置中需要调整的项，不是可独立提交的完整 INI。先准备三轮输入，再生成 31 → 32 的任务链；不要把本示例指向已有生产输出目录。

```ini
run_prepare_layout = true
run_prepare_tile_config = true
prepare_layout_stitching_workdir = new_joint_workdir
prepare_layout_round_manifest = /absolute/path/round_layout.csv
prepare_tile_config_stitching_workdir = new_joint_workdir
prepare_tile_config_source_channel_dir = ref/raw-refDAPI
prepare_tile_config_output_config = TileConfiguration.initial.txt
run_ashlar_joint_stitch = true
run_ashlar_joint_mosaic = true
ashlar_joint_stitch_stitching_workdir = new_joint_workdir
ashlar_joint_stitch_ref_channel_dir = ref/raw-refDAPI
ashlar_joint_stitch_if_channel_dir = IF/raw-DAPI
ashlar_joint_stitch_input_config = ref/TileConfiguration.initial.txt
ashlar_joint_stitch_if_input_config = IF/TileConfiguration.initial.txt
ashlar_joint_stitch_seqe_channel_dir = seqE/raw-DAPI
ashlar_joint_stitch_seqe_input_config = seqE/TileConfiguration.initial.txt
ashlar_joint_stitch_output_ref_config = TileConfiguration.registered.round001.AshlarJoint.txt
ashlar_joint_stitch_output_if_config = TileConfiguration.registered.IF.AshlarJoint.txt
ashlar_joint_stitch_output_seqe_config = TileConfiguration.registered.round011.AshlarJoint.txt
ashlar_joint_stitch_output_prefix = joint_round001-IF-round011

ashlar_joint_mosaic_stitching_workdir = new_joint_workdir
ashlar_joint_mosaic_channel_mode = LeicaIF
ashlar_joint_mosaic_channel_dir_prefix = IF/raw-
ashlar_joint_mosaic_input_config = TileConfiguration.registered.IF.AshlarJoint.txt
ashlar_joint_mosaic_ref_channel_dir = ref/raw-refDAPI
ashlar_joint_mosaic_ref_input_config = TileConfiguration.registered.round001.AshlarJoint.txt
ashlar_joint_mosaic_seqe_channel_dir_prefix = seqE/raw-
ashlar_joint_mosaic_seqe_input_config = TileConfiguration.registered.round011.AshlarJoint.txt
ashlar_joint_mosaic_tile_transform_json = joint_round001-IF-round011_summary.json
ashlar_joint_mosaic_stitch_result_dirname = stitching_results
ashlar_joint_mosaic_output_prefix = stitched_joint
ashlar_joint_mosaic_output_format = preserve
ashlar_joint_mosaic_make_3d = false
ashlar_joint_mosaic_slice_indices =
```

wrapper 主通道组始终对应 31 的 IF/moving 角色；`channel_mode` 只选择通道名称，因此旧双轮中将 seqE 当作 moving 的调用也保持此语义。新增 seqE 前缀才启用第三轮。未设置 seqE 输入时，31 保留两轮调用能力；IF 未另给 config 时仍使用参考 config。新生成的两轮 summary 也采用共同画布。32 仍可读取旧 summary：ref 不应用 IF 变换，IF 使用旧变换，两轮保留旧式独立画布；旧 summary 不可用于 seqE。不传 summary 时保留直接拼图的独立画布行为，不能宣称可直接叠加。

新三轮结果若用于reads整合，`cellreads_registration_if_dirname` 指向方法根，`cellreads_registered_tile_config` 采用本次 `TileConfiguration.registered.round001.AshlarJoint.txt` 及对应画布原点。参考轮改变时同步修改文件名，例如round005参考写为 `TileConfiguration.registered.round005.AshlarJoint.txt`。不能把新图像直接套在旧矩阵坐标上；本次代码扩展不重跑 reads 整合。

## 验证范围与历史记录

当前测试入口：`test_contracts/test_joint_stitching_contracts.py`（wrapper / generator）、`test_contracts/test_ashlar_tiff_readers.py`（真实灰度 TIFF reader）和 `test_contracts/test_joint_three_round_contracts.py`（真实合成 TIFF / CLI）。真实 reader / CLI 契约需激活 ashlar 环境以设置 Java，并在计算节点运行。reader 契约覆盖二维及 3/4/5/45 层、非正方形宽高、原位深、MIP/指定层/stack 像素和旋转。三轮 CLI 契约保留独立 FOV 清单、已知平移、小旋转、共同画布、实际地标、缺乏匹配失败及防覆盖检查，并增加 3 页堆栈案例，核对真实相对坐标、独立计算的画布范围和三轮地标叠加。测试使用 Ashlar 1.20.0；行为依据实际安装的 `ashlar/reg.py`，可对照[官方 v1.20.0 源码](https://github.com/labsyspharm/ashlar/blob/v1.20.0/ashlar/reg.py)。2026-11-19：9 项 wrapper/generator 契约通过；合成作业 5242827 的 3 项真实 TIFF 行为契约全部通过（18 秒、4 CPU 配额、计算线程 1）。首轮不同覆盖测试曾失败，定位并修正粗配准覆盖边界偏差后重测通过；未通过放宽坐标误差容限处理。诊断日志保存在项目 `02_Upstream/04_stitching/submit011_261123_205624_stitching_dev_validation/0001_261119_002916_joint_three_round_contracts/`。合成测试通过不等于 GBM 三轮真实数据已验收。

保留原说明中的历史事实：2026-10 的双轮版本曾记录 GBM001–016 连通、跨轮残差中位数 0.18–0.37 px，GBM006–009 约 1 px；GBM001/002 旋转约 −1.35°，GBM003–009、015 约 26–58 mdeg。旧说明还记录不同实现间绝对尺度最多约 60 ppm、跨轮整体平移约 0.3 px 的差异。这些是旧双轮版本的自洽性记录，本次未独立复算，也不能作为新三轮版本或生物学正确性的验收证据。

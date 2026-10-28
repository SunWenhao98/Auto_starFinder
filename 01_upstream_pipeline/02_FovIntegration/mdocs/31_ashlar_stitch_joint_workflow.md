# 3x Joint ref + IF Stitching 工作流说明

> 3x 是在原有 Fiji（1x）和 Ashlar（2x）流程之外**新增**的一条流程，原有流程不受影响：
> - `30_ashlar_stitch_mst.sh` / `p30_ashlar_stitch_mst.py`：单轮 ashlar，采用 MST 选边、一致性检查、环路复核和全局 LSQ（可选，用于 QC 或 TE 等单轮拼接）；
> - `31_ashlar_stitch_joint.sh` / `p31_ashlar_stitch_joint.py`：直接读原始的参考轮（ref round）和 IF 轮，由 MAF 生成名义坐标，把两轮的 FOV 放进同一个 ashlar 拼接问题一起求解，输出同一坐标系下的两份 TileConfiguration；
> - `32_ashlar_stitch_mosaic_joint.sh` / `p32_ashlar_stitch_mosaic_joint.py`：直接读原始数据，按联合坐标出图（可选平场校正）；
> - `p33_estimate_flat_field.py`（可选）：用多个样本合起来估计每个通道的平场，供 32 使用。

---

## 📋 文档定位

3x 流程的思路是：**ref 轮定义统一坐标系，联合拼接把 IF 轮放进这个坐标系。** 原来需要三条路径才能覆盖的情况，用这一条路径都能处理：

| 原路径 | 涉及步骤 | 3x 中对应的部分 |
|---|---|---|
| 逐 FOV IF→ref 配准，再生成 moving 坐标 | `nuclei_reg` (11) + `prepare_moveimages` (23) | 跨轮边 + 逐 FOV 偏移表 |
| IF 自拼接 + 大图整体平移 | `pyreg`/`matreg`/`reg_compare`/`transform_apply` (25/26/28/29) | 粗定位 + 联合求解 |
| IF 独立拼接（仅作展示） | `*Independent` channel mode | IF–IF 边 |

3x IF 流程（ini 里打开这两步即可）：

```text
ashlar_joint_stitch (31)   原始 ref 轮 DAPI + IF 轮 DAPI，MAF -> TileConfiguration.initial.txt + tile_summary.csv
                           -> TileConfiguration.joint_ref.txt + TileConfiguration.joint_IF.txt
ashlar_joint_mosaic (32)   原始数据出图：ref DAPI 用 joint_ref；IF 各通道用 joint_IF（加 IF tile 变换），画在 ref DAPI 的画布上
```

联合拼接不需要逐 FOV 配准，31/32 也直接读 `01_data` 里的原始文件，所以 `nuclei_reg` (11)、`prepare_tile_config` (12)、`prepare_layout` (21) 都不用跑，也不会生成它们的文件夹：`15_IFuint8_Fiji` 里配准、裁剪后的 ref-DAPI / DAPI / 蛋白图，`11_refRound1`、`12_IFuint8_Fiji_norefIF` 等 uint8 副本。GBM006 这样的文件夹每个约 120 GB。31 的工作目录（默认 `31_joint_ref_IF`）里只有坐标和结果：

```text
02_registration<suffix>/31_joint_ref_IF/
  TileConfiguration.initial.txt  tile_summary.csv                         （31，由 MAF 生成）
  TileConfiguration.joint_ref.txt  TileConfiguration.joint_IF.txt  joint_ref-IF_*   （31）
  stitching_results/stitched_joint_{refDAPI,561-CA9,488-CD144,647-CD31,DAPI}*.ome.tif   （32）
```

- **读哪些文件**：
  - ref 轮：`01_data/round%03d`（`ref_round`）`/PositionXXX/*ch03*.tif`。
  - IF 轮：`01_data/IF/PositionXXX/*ch0i*.tif`，通道 i 的顺序按 `channel_mode`，与 21 相同，LeicaIF 为 ch00=561-CA9、ch01=488-CD144、ch02=647-CD31、ch03=DAPI。
- **只用两轮都有的 Position**：只在一轮里有的 FOV 会列在日志里，不参与拼接。例如 GBM019 的 ref 轮去掉了 31 个 FOV，GBM021 的测序轮少拍了 7 个。
- **MAF 坐标按 Position 编号对应**：`p12_leica2Stitching_configuration.py` 是把排序后的第 i 个文件对应到第 i 个 MAF 点，缺号时会整体错位。所以 31 先用 Position001..M 的空占位文件跑 p12，再只保留实际使用的 FOV。p12 的参数和 position offset 与 12 相同；目前只支持 Leica（MAF）。
- **ref 轮是 uint16**：31/32 直接读取。32 输出 uint8 时的换算（÷65535×255）与原来 21 生成 uint8 副本时相同；平场校正在换算之前、用原始精度完成。

`ashlar_mst_stitch` (30) 不是必需步骤；需要单轮 mosaic 做检查，或拼 TE 等单轮数据时可以单独运行。

下游 reads 整合（`cellreads_registered_tile_config`）应使用 `TileConfiguration.joint_ref.txt`：转录本由 ref 轮 tile 的局部坐标加上 tile 位置得到，和 ref DAPI 图、蛋白图在同一块画布上，像素一一对应。

## 🔗 Runtime call chain

```mermaid
flowchart LR
    accTitle: Joint stitching runtime chain
    accDescr: The wrapper validates inputs and runs the Python joint stitcher, which reuses MSTEdgeAligner from p30, then the mosaic step stitches ref and IF channels with the joint configs.

    wrapper["31_ashlar_stitch_joint.sh"] --> py["p31_ashlar_stitch_joint.py"]
    py --> mst["p30_ashlar_stitch_mst.py: MSTEdgeAligner"]
    py --> cfg["TileConfiguration.joint_ref / joint_IF"]
    py --> shifts["joint_ref-IF_if_fov_shifts.csv"]
    py --> summary["joint_ref-IF_summary.json"]
    cfg --> mosaic["32_ashlar_stitch_mosaic_joint.sh -> p32"]
    summary -->|--tile_transform_json| mosaic
```

## ⚙️ 算法

1. **读入**：ref 和 IF 各 N 个 FOV 的 MIP，名义坐标都来自 `TileConfiguration.initial.txt`。tile 只读一次，缓存后各遍复用。
2. **粗定位**：把两轮 FOV 都按名义坐标缩小 16 倍拼成低分辨率图，用 FFT 互相关得到 IF 相对 ref 的整体偏移 D。D 只用来把 IF FOV 放到它实际拍到的 ref 区域上方，以便找到跨轮邻居；精度要求是几十 px 以内。
3. **联合求解（第 1 遍）**：2N 个 tile 交给 `MSTEdgeAligner`（`tile_group = ref/IF`）。邻接图自动包含 ref–ref、IF–IF、ref|IF 三类边；一致性检查按 `ref-H`、`ref-V`、`IF-H`、`IF-V`、`ref|IF` 分组；之后做环路复核、MST 连通检查和全局加权 LSQ（稳健剔除残差 > 3 px 的非桥边）。
4. **旋转估计**：用第 1 遍自己的 ref–ref 和 IF–IF 边，分别求出两轮的单轮位置 P、Q，再用所有可信的跨轮边稳健拟合相似变换 `z_ref = a·z_IF + b`。
5. **旋转校正**：|旋转| > `rotation_threshold_mdeg`（默认 10 mdeg）时，每个 IF FOV 绕自身中心按 a 重采样（线性插值，无数据处填 0；ashlar 拼图时会在 0 值处保留相邻 tile 的数据），然后重新联合求解，迭代到旋转估计的变化 < 1 mdeg（最多 3 遍）。P、Q 只取自第 1 遍（tile 尚未旋转）。

只平移 tile 无法表示旋转：小旋转会摊到每条接缝上，大旋转（例如载玻片重新放置，> 1°）会让跨轮匹配整体失败。

## 📤 输出（写在 stitching workdir）

| 文件 | 内容 |
|---|---|
| `TileConfiguration.joint_ref.txt` | ref FOV 在统一坐标系中的位置（**统一坐标框架**） |
| `TileConfiguration.joint_IF.txt` | IF FOV 在同一坐标系中的位置 |
| `joint_ref-IF_if_fov_shifts.csv` | 逐 FOV 的 IF→ref 配准：`ref_y/x`、`if_y/x`、`shift_y/x = IF − ref`、`if_rotation_mdeg`、`if_tile_transform_applied`。替代原来的逐 FOV 配准偏移 |
| `joint_ref-IF_summary.json` | 粗定位偏移、各类边的残差统计、旋转/尺度估计、`if_tile_transform`（若做了校正）、两张画布的原点关系 `if_canvas_to_ref_canvas_yx` |
| `joint_ref-IF_edge_alignment.csv`（以及 `_pass1_*`） | 每条边的配准、分组、是否可信、LSQ 残差 |
| `joint_ref-IF_coordinates.csv` | 2N 个 FOV 的最终坐标 |

**画布对应**：给了 `ref_input_config` 时，32 用 joint_ref 的画布（原点和大小）画 IF 各通道（p32 `--canvas_config`），所有通道和 reads 像素对齐，超出 ref 范围的 IF 部分被裁掉，和原来 24 一样。单独按 joint_IF 出图时，画布原点是它自己的最小坐标，`ref 画布像素 = IF 画布像素 + if_canvas_to_ref_canvas_yx`。

**IF 通道出图**：`32_ashlar_stitch_mosaic_joint.sh --tile_transform_json joint_ref-IF_summary.json`，json 里没有 `if_tile_transform` 时自动不做变换。

**接缝偏暗与平场校正**：视野边缘比中心暗（488/647 上、左边缘有一条陡的暗带，四角约为中心的 0.8），重叠区正好是两张 FOV 的边缘，拼出来接缝会暗 5–10%。
- `--flat_field auto`：每个通道用本样本全部 FOV 的 MIP 平均（高斯 64 px）作平场，在读图时、旋转和 IF 变换之前，每张 FOV 先除以平场，再转回原整数类型。
- `--flat_field <目录>`：使用 `p33_estimate_flat_field.py` 由多个样本合起来估计的平场（`<目录>/<通道>.tif`，如 `647-CD31.tif`、`refDAPI.tif`）。
- 默认 `none`：不校正，保持原行为。

GBM001–022 的平场形状一致，用其他样本合并估计的平场和用本样本平场的效果相同。另外，32 会把 ashlar 混合后的像素四舍五入后再写回整数 mosaic：ashlar 原本是截断取整，暗通道的接缝会因此再暗约 3%。两项都做之后，GBM001 / GBM006 的 488、647 接缝亮度从 0.91–0.92 回到 0.98–1.00。

## 🔧 ini 配置（`batch_config.upstream.ini`）

```ini
run_ashlar_joint_stitch = true
run_ashlar_joint_mosaic = true

; 名义坐标沿用 prepare_tile_config_* 的载物台参数（maf_file、pixel_size_um、overlap_ratio ...），
; position offset 由 [DEFAULT].samples 按样本顺序累计，与 12 相同；ref 轮为 round%03d（ref_round）
ashlar_joint_stitch_stitching_workdir = 31_joint_ref_IF
ashlar_joint_stitch_if_round = IF
ashlar_joint_stitch_ref_channel_token = ch03
ashlar_joint_stitch_if_channel_token = ch03
ashlar_joint_stitch_rotation_threshold_mdeg = 10

ashlar_joint_mosaic_channel_mode = LeicaIF
ashlar_joint_mosaic_input_config = TileConfiguration.joint_IF.txt
ashlar_joint_mosaic_tile_transform_json = joint_ref-IF_summary.json
ashlar_joint_mosaic_ref_input_config = TileConfiguration.joint_ref.txt   ; 留空则不出 ref DAPI 图
ashlar_joint_mosaic_flat_field = auto      ; none | auto | 平场目录

cellreads_registration_if_dirname = 31_joint_ref_IF
cellreads_registered_tile_config = TileConfiguration.joint_ref.txt
```

reads 整合读取 `<if_dirname>/TileConfiguration.initial.txt`、`tile_summary.csv` 和 `TileConfiguration.joint_ref.txt`，三者都由 31 写在它的工作目录里。

## ✅ 验证（GBM001–016、GBM019–021，2026-10）

- 名义坐标：14 个样本由 MAF 生成的 `TileConfiguration.initial.txt` 与原流程（12）的结果逐字一致。GBM019 / GBM021 两轮 FOV 不同，与原流程 ref 路径的坐标一致，GBM019 差一个整体平移。GBM007 / GBM008 原流程里手动去掉了 8 / 4 个 FOV，这里保留全部 FOV，其余坐标一致。
- 直接读原始数据（ref 轮 uint16）与读 21 生成的 uint8 副本相比，同一代码的联合拼接位置差中位数 ≤ 0.014 px、最大 ≤ 0.14 px。

- 16 个样本全部连成一个整体。跨轮残差中位数 0.18–0.37 px；GBM006–009 约 1 px（IF 轮整体偏约 1.5 个 FOV，跨轮边都是半重叠，加上两轮视野内存在约 0.1% 的几何差异，按决定未做校正）。
- 边缘和中心的跨轮残差一致，没有随距离累积。
- GBM001/002 两轮之间旋转约 −1.35°，只有经过自动旋转校正才能对上；GBM003–009、015 的旋转为 26–58 mdeg，校正后接缝回到 0.15–0.38 px。
- 以上都是**自洽性指标**，不是 ground truth。和"使用两轮单轮拼接结果做粗定位与旋转估计"的早期实现相比：
  - 旋转估计一致（≤ 0.3 mdeg），跨轮残差相当或略低；
  - 但整个坐标系的绝对尺度有最多约 60 ppm 的差异（2.5 万 px 拼图边缘约 1–2 px），ref 与 IF 之间有约 0.3 px 的整体平移差异；
  - 这些差异在配准本身的不确定性范围内，不影响 ref↔IF 的对应关系。

## ⚠️ 注意

- 没有 ref 轮数据的样本无法使用这条流程。
- 稳健剔除只删除"非桥"边，不会造成 FOV 断连；但如果模型本身不对（例如旋转很大却没有校正），可能会成片删除跨轮边，此时应检查 summary 中 `ref|IF` 的 `lsq_removed` 数量。

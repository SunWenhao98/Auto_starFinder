# 逐轮邻域强度筛选与证据缓存

> 本文记录 schema v1 / 27 体素筛选版本。现行同层九像素筛选、五邻域双比例记录及 schema v2 请见同目录 `0002_261031_122559_plane9_neighborhood_evidence.md`。旧缓存的邻域含义保持不变。

`intensityThresh_PR` / `IntensityThresh_perRound` 现在表示：**所有请求的解码轮次**，每轮至少一个通道的空间邻域强度和达到该阈值。等号通过；中心像素仅记录。以前仅参考轮参与，非零参数的行为已经改变。

`voxel_size=[1,1,1]` 是半径，内部点含27体素。研究扫描 `0/108/216/324/432/540`，即0或 `(5/10/15/20/25)*27*0.8`。0.8只缩放总和阈值，不表示80%像素各自通过。边缘按实际窗口记录体素数，仍执行固定sum门槛。请求轮次不足时失败，不静默缩短barcode。

## 常规调用与缓存

完整 `batch_config.upstream.ini` 的 `gd_intensityThresh_PR`、`gd_voxelsize`、`gd_decoding_rounds` 原样传给wrapper；新增 `gd_save_decode_evidence` 默认false，旧INI省略也保持false。wrapper对应 `--save_decode_evidence true`，MATLAB对应 logical `save_decode_evidence=true`。

MATLAB直接调用默认PR仍为270，wrapper和完整INI默认仍为0；研究配置必须显式给定实际阈值和窗口。没有改变平均quality与码本匹配规则，也没有删除重复XYZ。

开启缓存目前要求tri及完整11轮。建议在PR=0提取一次，得到：

- `decode_evidence_<method>_<spot threshold>_tri_PR0/evidence.mat`：全部原始候选ID、坐标、每轮强度/quality/颜色、码本索引、质量和当前PR通过掩码、实际邻域体素数。
- 同目录 `metadata.json`：实际参数、输入路径、码本序列和基因索引。强度来自已预处理/配准图像，不是相机原始灰度。

`candidate_id` 是allSpots原始1-based行号，与sample和position联合使用。重复XYZ继续占各自候选行。导出前核验这些掩码和码本匹配可逐行复现当前goodSpots/goodReads。

缓存目录存在即失败。**旧goodPoints、raw诊断表及日志文件名大多不含PR，直接重跑必须使用独立的新registration目录。** 只建立MAT/allSpots文件级链接；输出保存在新目录，避免链接整个旧registration目录。

## 多阈值评估

`01_spotDecoding/p05_evaluate_pr_thresholds.py` 接收 `--evidence_dir` 和 `--output_dir`，默认扫描六个阈值；后者必须不存在。HDF5分块读取，无需重复读取图像。示例：

```bash
python -u /absolute/pipeline/01_spotDecoding/p05_evaluate_pr_thresholds.py \
    --evidence_dir /absolute/new_registration/Position001/decode_evidence_max3d_0.2_tri_PR0 \
    --output_dir /absolute/new_threshold_results
```

每个PR目录输出候选身份对应的goodPoints、固定码本全集的基因计数、逐轮失败统计和summary。原cache的PR掩码不预过滤新扫描，quality仍按提取时规则。计数保留记录；uniqueXYZ只作附加诊断。

固定候选产率分母为全部原始候选；条件解码率分母为质量与强度共同通过的候选。totalRNA仅合并基因末尾_rbRNA/_ntRNA；零计数保留。阈值间相关性使用固定totalRNA基因全集及log2(count+1)，参照最低输入阈值，默认0。

这个入口不运行分割、注释、外部Ivy Atlas或随机删点对照；这些属于后续九样本研究。相关性和保留数量不能单独证明准确率。

## 迁移边界与验证

迁入分块/向量化提速、完整raw cell初始化、非方图像邻域边界、DFTApply3D负位移边界+1。DFT修复只影响未来重新配准；读取既有MAT的阈值研究不受其影响。

未迁入exact XYZ删除、Gaussian、局部背景校正、subpixel或smoke Max3D定位更改。历史rawReads可能缺行或有异常空单元，不能按行号强拼旧表；新增缓存保留完整候选身份。

本轮正式实施清单与验证证据位于GBM项目：
`/gpfs/share/home/2401111558/01_project/08_projGBM/.omo/plans/0097_261031_112558_decode_pr_code_migration.md`，
`/gpfs/share/home/2401111558/01_project/08_projGBM/registration/0001_261031_112558_decode_pr_validation/`。

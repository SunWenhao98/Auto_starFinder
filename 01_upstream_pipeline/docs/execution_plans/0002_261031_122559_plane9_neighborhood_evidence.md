# 同层九像素筛选与五邻域证据

主筛选为原 XYZ 当前 z 层 3×3 的最大通道强度和，全部请求轮次均须达到 `intensityThresh_PR`，等号通过。tri 研究使用完整 11 轮。研究默认网格为 0/36/72/108/144/180，分别对应 μ=0/5/10/15/20/25 与 `μ×9×0.8`。参数接收实际总和阈值，不直接接收 μ。

`gd_voxelsize` / `voxel_size` 继续控制颜色解码窗口，本研究显式使用 `[1,1,1]` 保留 27 体素 `colorSeq`、质量评分和 barcode。筛选窗口独立固定为同层九像素，不通过改动颜色窗口实现。MATLAB、wrapper 和完整 INI 的 PR 默认值统一为 0；研究应显式给定参数。

## 五种邻域与两种比例

固定顺序为 `center1,cross5,plane9,volume19,volume27`：中心；同层中心加四邻；同层完整 3×3；完整 3×3×3 去掉八角；完整 3×3×3。19 为当前层 9 加上下层十字各 5。窗口中心固定，不逐轮重新找峰。边界仅使用实际存在位置，并记录每邻域实际体素数；筛选仍用固定九像素门槛。

每候选、每轮、每邻域记录三个通道的总和 S、L1 占比 `S_c/sum(S)` 和 L2 值 `S_c/(sqrt(sum(S.^2))+1e-6)`。三通道全零时 L1 为 NaN、L2 为零，并记录零信号标记；不把零信号解释为各占 1/3。并列优势另报。两种比例仅作诊断，不新增比例门槛。诊断以 single 保存，颜色解码仍保持现有 double 计算。

## 缓存与回放

使用完整 `batch_config.upstream.ini`，`gd_save_decode_evidence=true` 对应 wrapper `--save_decode_evidence true`；旧配置省略时仍为 false。建议 PR=0 一次提取全部候选，输出新目录 `decode_evidence_v2_plane9_<method>_<spot threshold>_tri_PR0/`。

schema v2 新增五邻域的 S/L1/L2、实际体素数、零信号和逐轮 plane9 信号。各通道矩阵采用二维展平，列序为 round、neighborhood、channel（channel 最快）；metadata 明确此顺序、邻域名称、公式、精度、筛选邻域和解码窗口。旧 intensity 列及 neighbor_voxel_count 继续描述颜色解码窗口，不能解释为 plane9。

`candidate_id` 为 allSpots 原始 1-based 行号，与 sample、position 联合使用；重复 XYZ 保留各自记录。exporter 核验质量、plane9 强度与码本掩码能够逐行复现 core goodSpots/goodReads。

`01_spotDecoding/p05_evaluate_pr_thresholds.py` 以 `--evidence_dir`、`--output_dir` 输入输出，`--intensity_neighborhood plane9` 为主方案，`volume27` 为对照。`--thresholds` 如提供则为实际 S 阈值；省略时按所选邻域使用 μ=0/5/10/15/20/25、名义像素数和0.8换算。比较应使用同 μ，不应把两个邻域的同一个实际 PR 当作等强度条件。

旧 v1 缓存仅可用于明确选择的 volume27 对照，且原 `voxel_size` 必须为 `[1,1,1]`；其他旧解码窗口不得误标为27体素。旧缓存不能还原 center1 各通道或 cross5/plane9/volume19。plane9 请求遇到旧缓存必须失败；不猜算、不均分。新增证据必须重新读取一次 MAT，六阈值不重复读取图像。

## 输出与解释

保留有效记录数、唯一 XYZ 附加计数、条件解码率和固定候选产率；固定候选产率的分母为全部原候选，条件解码率的分母为质量与强度共同通过的候选。码本基因全集保留零计数，totalRNA 合并末尾 rbRNA/ntRNA，计数相关性使用固定基因全集的 log2(count+1)。

新增各邻域/轮次通道 S/L1/L2 汇总、零信号与并列计数、plane9 与 volume27 胜出通道一致性，以及相同 μ 的都通过/仅9通过/仅27通过/都不通过统计。9 与27胜出通道不同不额外过滤，但必须单列。更高强度或相关性不直接等于准确率提高。

旧 goodPoints、raw 表和日志文件名多不含邻域及 PR；每次直接解码必须使用新的实体 registration 输出，MAT/allSpots 仅做文件级输入软链接。新缓存与回放输出存在时拒绝覆盖。旧数据、旧缓存及旧结果不修改。

本次范围为代码、必要测试和 GBM004/Position016 技术验证；九样本全量、Ivy GBM Atlas 外部参考相关性、分割及注释闭环、完整 PPT/HTML 研究报告属于后续研究。Ivy 不是这些患者的配对 Bulk。exact XYZ 不去重，Gaussian、局部背景、subpixel 和 smoke Max3D 定位改动未纳入。

项目正式计划：`/gpfs/share/home/2401111558/01_project/08_projGBM/.omo/plans/0098_261031_122559_plane9_neighborhood_evidence.md`。

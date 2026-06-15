mkdir -p zz_decoding
cd zz_decoding
python /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/99_logExtraction/01_parse_globalDecoding_results.py --dir /gpfs/share/home/2401111558/01_project/08_projGBM/02_Process/03_starFinder/20260428_submit001_GBM0407_DecodeNormal

mkdir ../zz_summarydata
cd ../zz_summarydata
python /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/99_logExtraction/02_summary_decoding.py --dir /gpfs/share/home/2401111558/01_project/08_projGBM/02_Process/03_starFinder/20260428_submit001_GBM0407_DecodeNormal


## 统一日志提取与汇总工具（新增）

新增两个主工具：

- `parse_pipeline_logs.py`：从 batch root 下的 `submit*` 子目录自动寻找固定日志目录，生成 per-submit CSV。
- `summarize_pipeline_logs.py`：读取对应 `zz_*` 目录内的 per-submit CSV，并在该目录内部创建 `zz_sum*` 汇总目录。

### 固定映射

| log_type | 日志目录 | parser 输出目录 | summary 输出目录 |
| --- | --- | --- | --- |
| `decoding` | `logs_global_readDecoding` | `zz_decoding` | `zz_decoding/zz_sum_decoding` |
| `global_spf` | `logs_global_spot_finding` | `zz_globalspf` | `zz_globalspf/zz_sum_globalspf` |
| `dapi_cp` | `logs_dapi_segmentation` | `zz_dapicp` | `zz_dapicp/zz_sum_dapicp` |
| `gr_shift` | `logs_global_registration` | `zz_grshift` | `zz_grshift/zz_sum_grshift` |

### 基本用法

只需要输入 batch root 和 `log_type`：

```bash
python /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/00_utils/99_logExtraction/parse_pipeline_logs.py \
  --batch-root /gpfs/share/home/2401111558/01_project/08_projGBM/02_Upstream/03_starFinder/20260606_submit001_GBM0421p1_SpotDecode \
  --log-type decoding

python /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/00_utils/99_logExtraction/summarize_pipeline_logs.py \
  --batch-root /gpfs/share/home/2401111558/01_project/08_projGBM/02_Upstream/03_starFinder/20260606_submit001_GBM0421p1_SpotDecode \
  --log-type decoding
```

把 `--log-type decoding` 替换为 `global_spf`、`dapi_cp` 或 `gr_shift` 即可处理对应日志类型。

### 输出说明

- parser 输出：`<batch-root>/<zz_dir>/<submit_name>_<log_type>_results.csv`
- summarizer 输出：`<batch-root>/<zz_dir>/<zz_sum_dir>/`
- 单指标 summary 会保留，便于后续可视化脚本逐指标比较。
- `gr_shift` 的 `time`、`dx`、`dy`、`dz` 分别保存和汇总，不使用 `(time; dx; dy; dz)` 这类字符串打包格式。
- `PositionXXX` 按 `XXX` 数字排序，避免 `Position010` 排在 `Position002` 前面。

### 注意事项

- 旧脚本保持不动；新增工具不依赖 `pandas`。
- 若某个 `submit*` 下没有对应日志目录，会打印警告并跳过，不会中断整个批次。
- 若整个 batch root 下没有可处理日志，会创建对应输出目录并提示 `未找到可处理日志` 或 `未找到可汇总 CSV`。

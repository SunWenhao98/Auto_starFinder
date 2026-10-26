## 统一日志提取与汇总工具（新增）

新增两个主工具：

- `parse_pipeline_logs.py`：从 batch root 下的 `submit*` 子目录自动寻找固定日志目录，生成 per-submit CSV。
- `summarize_pipeline_logs.py`：读取对应 `zz_*` 目录内的 per-submit CSV，并在该目录内部创建 `zz_sum*` 汇总目录。

### 固定映射

| log_type | 日志目录 | parser 输出目录 | summary 输出目录 |
| --- | --- | --- | --- |
| `decoding` | `logs004_global_readDecoding` | `zz_decoding` | `zz_decoding/zz_sum_decoding` |
| `global_spf` | `logs004_global_spot_finding` | `zz_globalspf` | `zz_globalspf/zz_sum_globalspf` |
| `dapi_cp` | `logs_dapi_segmentation` | `zz_dapicp` | `zz_dapicp/zz_sum_dapicp` |
| `gr_shift` | `logs001_global_registration` | `zz_grshift` | `zz_grshift/zz_sum_grshift` |

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


## 旧/新解码入口兼容（2026-10-16）

- 保留原CLI、CONFIGS主目录名及CSV schema；自动识别 `logs004_global_readDecoding` 或 `logs004_global_reads_decoding`。同一submit若两者并存则报错，避免重复统计。
- decoding与gr_shift均识别旧中文Position标记或 `POSITION_NAME=PositionXXX`；decoding仍逐行流式读取，不复制原始日志。
- parser/summarizer仍可能覆盖同名CSV；批量执行入口必须先检查输出目录不存在，不对正式结果直接重复运行。
- 通用绘图脚本位于本目录上一级 `00_utils/plot_decoding_qc_generic.py`；从项目现有同名脚本复用，原项目脚本及GBMp4专用plot_spotDeocde.py不改动。
- 必填 `--batch-root`；沿用 `--zz-decoding`、`--output-dir`、`--crosstalk-cutoff`、`--dpi`。新增 `--group_by sample|condition`，默认condition保留按条件分组；同一参考轮多样本QC显式传sample。
- 按样本分组时，输出condition为样本名，source_condition保留从文件名推断的原始条件标签。绘图输出目录已存在时拒绝覆盖。
- 复用六指标、Crosstalk>0.8标记及绘图过滤规则，PNG-only、300dpi；不删除数据或自动剔除FOV。

```bash
python parse_pipeline_logs.py --batch-root /path/to/batch --log-type decoding
python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type decoding
python ../plot_decoding_qc_generic.py --batch-root /path/to/batch --group_by sample
```

这些命令用于已检查输出边界的计算节点作业；不自动提交SLURM。

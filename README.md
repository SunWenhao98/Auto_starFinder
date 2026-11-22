# Auto_starFinder
An automated, SLURM-based batch-processing pipeline for  image-based high-throughput spatial-omics data. It dynamically generates dependency-aware job scripts from a single configuration file for scalable multi-sample analysis.

## CellReads 矩阵与独立 points 输出

`01_upstream_pipeline/04_CellReadsIntegration/csv2CountMatrix.py` 保持 `--input_csv` 和 `--output_h5ad` 接口及原有稠密 `.X`、`rbRNA`、`ntRNA` 矩阵、细胞/基因顺序。h5ad 不再包含 `uns["points"]`；分子表保存到同目录的 `<h5ad stem>_points.parquet`，不保存 DataFrame 索引。分子表仍只保留 `cell_barcode != 0` 的行，并沿用 `gene_name → feature_name`、`column → x`、`row → y` 的列名转换；行顺序、重复分子和其他列保留。写出 Parquet 后释放分子表，再保存 h5ad。任一同名输出已存在时拒绝覆盖。

例如 `adata_GBM001_clustermap_test.h5ad` 对应 `adata_GBM001_clustermap_test_points.parquet`。原 `02_csv2CountMatrix.sh` 无需改变调用参数。此修改只影响后续转换，不迁移或改写已有 h5ad。

GBM 下游 `001`/`001b` 已在读取后判断 points 是否存在；无内嵌 points 时继续正常执行 QC/TE（及 `001b` 的共同基因筛选和 PCA），不读取、复制或重新导出独立 Parquet，也不在下游 summary 中新增 `points_parquet`。后续需要分子坐标时，应直接引用上游 Parquet，并依据目标对象的 `original_barcode` 与基因列表另行筛选。

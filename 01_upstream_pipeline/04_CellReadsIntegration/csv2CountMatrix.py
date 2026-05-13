import os
import sys
import argparse
import pandas as pd
import numpy as np
import anndata as ad
from pathlib import Path

if __name__ == '__main__':

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Convert CSV file to AnnData object')
    parser.add_argument('--input_dir', type=str, help='Path to CSV file')
    args = parser.parse_args()

    # 读取 CSV 文件并提取信息
    output_path = args.input_dir
    input_dir = Path(args.input_dir)
    molecular_files = list(input_dir.glob('remain_reads_*.csv'))

    if not molecular_files:
        print(f"错误: 在 {input_dir} 中未找到 remain_reads_*.csv 文件")
        sys.exit(1)

    molecular_file = molecular_files[0]
    suffix = molecular_file.stem.replace('remain_reads_', '')

    print(f"Reading molecular file from: {molecular_file}")
    print(f"文件名: {molecular_file.name}")
    print(f"后缀: {suffix}")


    # mol =pd.read_csv(molecular_file, index_col=0)
    mol = pd.read_csv(molecular_file)
    print("molecular_loaded")
    print("Current column names of the dataframe: ", mol.columns.tolist())

    #rename gene to feature_name
    mol = mol.rename(columns={'gene_name': 'feature_name'})
    mol = mol.rename({'column':'x','row':'y'}, axis=1)
    print(mol.head())
    print("Current column names of the dataframe: ", mol.columns.tolist())

    mol_filtered = mol[mol['cell_barcode'] != 0]
    # print("Current column names of the dataframe: ", mol_filtered.columns.tolist())

    # count_df = mol_filtered.groupby(['cell_barcode', 'feature_name']).size().unstack(fill_value=0)

    # adata = ad.AnnData(X=count_df.values)
    # adata.obs['cell_id'] = count_df.index.astype(str)
    # adata.var['feature_name'] = count_df.columns.astype(str)
    # adata.uns["points"]=mol
    # adata.obs_names = adata.obs['cell_id']
    # adata.var_names = adata.var['feature_name']
    # adata.write_h5ad(f'{output_path}/adata_{suffix}.h5ad')
    # adata



    total_counts = mol_filtered.groupby(['cell_barcode', 'gene']).size().unstack(fill_value=0)

    rb_filtered = mol_filtered[mol_filtered['feature_name'].str.endswith('_rbRNA')]
    nt_filtered = mol_filtered[mol_filtered['feature_name'].str.endswith('_ntRNA')]
    rb_counts = rb_filtered.groupby(['cell_barcode', 'gene']).size().unstack(fill_value=0)
    nt_counts = nt_filtered.groupby(['cell_barcode', 'gene']).size().unstack(fill_value=0)

    # 维度对齐：极其重要的一步！
    # 因为某些基因可能只被检测到了 rbRNA 而没有 ntRNA，直接生成的矩阵列数可能不一致。
    # 使用 reindex 强制将 rb 和 nt 矩阵的行(细胞)和列(基因)与 total_counts 严格对齐，缺失的补 0。
    rb_counts = rb_counts.reindex(index=total_counts.index, columns=total_counts.columns, fill_value=0)
    nt_counts = nt_counts.reindex(index=total_counts.index, columns=total_counts.columns, fill_value=0)

    adata = ad.AnnData(X=total_counts.values)
    adata.obs_names = total_counts.index.astype(str)
    adata.var_names = total_counts.columns.astype(str)

    adata.layers['rbRNA'] = rb_counts.values
    adata.layers['ntRNA'] = nt_counts.values
    adata.uns["points"] = mol_filtered 

    adata.write_h5ad(f'{output_path}/adata_{suffix}.h5ad')
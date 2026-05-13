# generate_orthogonal.py
import os
import numpy as np
import configparser
from itertools import product
from pyDOE2 import lhs

# ---------------------- 基础设置 ---------------------- #
project_root = os.getcwd()
output_root = os.path.join(project_root, "orthogonal_outputs")
os.makedirs(output_root, exist_ok=True)

# 参数设置（默认值 + 步长）
def_param = {
    "fidelity": 350,
    "sparsity": 15,
    "sparse_iter_total": 14,
    "percennorm_high": 99.95,
    "background": [0, 1],
    "enable_refineResolution": ["False", "True"]
}

step_size = {
    "fidelity": 50,
    "sparsity": 5,
    "sparse_iter_total": 4,
    "percennorm_high": 0.025
}

levels = 5

# ---------------------- 正交设计生成 ---------------------- #
def generate_levels(center, step, n):
    half = n // 2
    return [round(center + (i - half) * step, 3) for i in range(n)]

def create_orthogonal_table():
    fid_levels = generate_levels(def_param["fidelity"], step_size["fidelity"], levels)
    spa_levels = generate_levels(def_param["sparsity"], step_size["sparsity"], levels)
    ite_levels = generate_levels(def_param["sparse_iter_total"], step_size["sparse_iter_total"], levels)
    per_levels = generate_levels(def_param["percennorm_high"], step_size["percennorm_high"], levels)
    ref_levels = def_param["enable_refineResolution"]
    bg_levels = def_param["background"]

    # 正交设计（使用拉丁超立方近似模拟正交试验）
    design = lhs(4, samples=9, criterion='maximin')
    design = np.floor(design * levels).astype(int)

    table = []
    for i, row in enumerate(design):
        fid = fid_levels[row[0]]
        spa = spa_levels[row[1]]
        ite = ite_levels[row[2]]
        per = per_levels[row[3]]

        if i in [0, 1, 2, 5, 6]:  # 低背景
            bg = bg_levels[0]
        else:
            bg = bg_levels[1] if bg_levels[0] == 0 else bg_levels[1] + 1

        ref = ref_levels[i % 2]  # 简单交替

        table.append({
            "round": f"round{str(i+1).zfill(3)}",
            "fidelity": fid,
            "sparsity": spa,
            "sparse_iter_total": ite,
            "percennorm_high": per,
            "background": bg,
            "enable_refineResolution": ref
        })
    return table

# ---------------------- 配置文件写入 ---------------------- #
def write_config(table):
    for entry in table:
        outdir = os.path.join(output_root, entry["round"])
        os.makedirs(outdir, exist_ok=True)

        for lvl in [1, 2]:
            config = configparser.ConfigParser()
            config.optionxform = str

            config["PROJECT"] = {"step_size": str(step_size["fidelity"])}
            config["PROCESSING"] = {"pixelsize": "108.33", "percennorm_high": str(entry["percennorm_high"]) }
            config["UPSAMPLING"] = {}
            config["SPARSING"] = {
                "chunksize_sparse": "2304",
                "resolution": "300",
                "numerical_aperture": "1.42",
                "fidelity": str(entry["fidelity"]),
                "sparsity": str(entry["sparsity"]),
                "hessian_iter": "100",
                "sparse_iter_total": str(entry["sparse_iter_total"]),
                "overlap": "60",
                "decon_type": "1",
                "continuity": "0.1",
                "background": str(entry["background"]),
                "enable_refineResolution": str(entry["enable_refineResolution"]),
                "enable_Guassblur": "False",
                "enable_upsample": "False"
            }
            outpath = os.path.join(outdir, f"config_level{lvl}.ini")
            with open(outpath, 'w') as cf:
                config.write(cf)

# ---------------------- 文件列表生成 ---------------------- #
def write_filelist(table, base_path):
    for entry in table:
        r = entry["round"]
        rid = int(r[-3:])
        if rid in [1, 2, 3, 6, 7]:
            bgtype = "low"
        else:
            bgtype = "high"
        line = f"find {base_path}/{r} -type f -name \"*.tif\" | sort -V > {output_root}/{r}/filelist.txt"
        with open(os.path.join(output_root, f"generate_filelist_{bgtype}.sh"), 'a') as f:
            f.write(line + "\n")

# ---------------------- sbatch 提交脚本生成 ---------------------- #
def write_submit_all(table):
    with open(os.path.join(output_root, "submit_all.sh"), 'w') as fout:
        fout.write("#!/bin/bash\n")
        for part in [[1,2,3,6,7], [4,5,8,9]]:
            for r in part:
                rname = f"round{str(r).zfill(3)}"
                jobname = f"decon_{rname}"
                fout.write(
                    f"sbatch -J {jobname} --array=1-912%8 submit_decon.sh \\\n  $RAW/{rname} \\\n  $OUT/{rname} \\\n  $TEMP \\\n  {output_root}/{rname}/filelist.txt \\\n  {output_root}/{rname}/config_level2.ini\n"
                )
            fout.write("wait\n")

# ---------------------- 主流程 ---------------------- #
if __name__ == '__main__':
    table = create_orthogonal_table()
    write_config(table)
    write_filelist(table, base_path="$RAW")
    write_submit_all(table)
    print("正交测试配置已生成，包含配置文件、文件列表和提交脚本。")

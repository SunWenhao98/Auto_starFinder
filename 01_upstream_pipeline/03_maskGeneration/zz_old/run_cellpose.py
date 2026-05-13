import argparse
import numpy as np
import tifffile
from cellpose import models, io
import torch
import time
import os
import matplotlib.pyplot as plt

def percennorm(img, miper=0, maper=100):
    """百分位归一化，增强对比度"""
    img = np.array(img, dtype='float32')
    datamin = np.percentile(img, miper, method='midpoint')
    datamax = np.percentile(img, maper, method='midpoint')
    output = (img - datamin) / (datamax - datamin)
    output[output > 1] = 1
    output[output < 0] = 0
    return output

def run_segmentation_maxproj(dapi_path, output_base_path, diameter, no_gpu, model_type='nuclei'):
    """
    1. 读取 3D DAPI
    2. 执行最大投影 (Max Projection)
    3. 运行 2D Cellpose
    4. 保存 2D Mask (TIF & NPY)
    """
    # 1. 检查 GPU
    use_gpu = not no_gpu and torch.cuda.is_available()
    device_name = "GPU" if use_gpu else "CPU"
    print(f"--- Starting 2D Max-Projection Segmentation on {device_name} ---")

    # 2. 读取图像
    print(f"Loading 3D DAPI stack: {dapi_path}")
    dapi_stack = io.imread(dapi_path) 

    print(f"Original shape: {dapi_stack.shape}")

    # 3. 生成最大投影
    if dapi_stack.ndim == 3:
        print("Performing Max Projection along Z-axis...")
        # 假设数据格式为 (Z, Y, X)，沿轴 0 投影
        dapi_2d = np.max(dapi_stack, axis=0)
    elif dapi_stack.ndim == 2:
        print("Image is already 2D.")
        dapi_2d = dapi_stack
    else:
        raise ValueError(f"Unsupported image dimensions: {dapi_stack.ndim}")

    # 4. 预处理 (归一化)
    print("Normalizing image...")
    dapi_2d_norm = percennorm(dapi_2d, 1, 99.8) 

    # 5. 初始化模型
    # 【修复】改回 CellposeModel，这是更通用的类名
    print(f"Initializing Cellpose '{model_type}' model...")
    model = models.CellposeModel(gpu=use_gpu, model_type=model_type)

    # 6. 运行 2D 分割
    # 如果 diameter=0，Cellpose 会自动估算
    diam_arg = None if diameter == 0 else diameter
    print(f"Running 2D segmentation (Diameter={diameter if diameter>0 else 'Auto'})...")
    
    start_time = time.time()
    
    # CellposeModel.eval 的参数略有不同，通常不需要 flow_threshold 用于 nuclei
    # 但为了兼容性，我们保留常用参数
    masks, flows, styles = model.eval(
        dapi_2d_norm, 
        diameter=diam_arg, 
        channels=[0, 0],
        flow_threshold=None, # nuclei 模型通常设为 None 或 0.4
        do_3D=False 
    )
    end_time = time.time()
    print(f"Segmentation finished in {end_time - start_time:.2f} seconds.")
    print(f"Detected {masks.max()} cells.")

    # 7. 保存输出
    output_dir = os.path.dirname(output_base_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    output_tif_path = output_base_path + ".tif"
    output_npy_path = output_base_path + ".npy"
    output_png_path = output_base_path + "_qc.png"

    # 7a. 保存 TIF Mask (2D)
    print(f"Saving 2D mask TIF: {output_tif_path}")
    io.imsave(output_tif_path, masks)

    # 7b. 保存 NPY (2D) - Baysor 预处理脚本将读取这个
    print(f"Saving 2D mask NPY: {output_npy_path}")
    np.save(output_npy_path, masks)

    # 7c. 保存 QC 图片 (原图 + 轮廓)
    print(f"Saving QC image: {output_png_path}")
    # 关闭交互模式以防在集群上报错
    plt.ioff()
    fig = plt.figure(figsize=(12, 12))
    plt.imshow(dapi_2d_norm, cmap='gray')
    # 绘制轮廓
    from cellpose import plot
    outlines = plot.utils.outlines_list(masks)
    for o in outlines:
        plt.plot(o[:,0], o[:,1], color='r', linewidth=1)
    plt.axis('off')
    plt.savefig(output_png_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print("\n--- Process completed successfully! ---")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run 2D Cellpose on Max Projected DAPI.")
    parser.add_argument('--input', type=str, required=True, help='Path to the 3D DAPI TIFF stack.')
    parser.add_argument('--output_base', type=str, required=True, help="Base path for outputs.")
    parser.add_argument('--diameter', type=float, default=0, help='Estimated NUCLEI diameter. 0 for auto.')
    parser.add_argument('--no-gpu', action='store_true', help='Disable GPU usage.')
    
    args = parser.parse_args()
    
    run_segmentation_maxproj(args.input, args.output_base, args.diameter, args.no_gpu)
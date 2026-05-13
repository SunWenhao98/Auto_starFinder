import argparse
import numpy as np
import tifffile
from cellpose import models, io, plot
import torch
import time
import os
import matplotlib.pyplot as plt
import pandas as pd
import cc3d

def percennorm(img, miper=0, maper=100):
    img = np.array(img, dtype='float32')
    datamin = np.percentile(img, miper, method='midpoint')
    datamax = np.percentile(img, maper, method='midpoint')
    output = (img - datamin) / (datamax - datamin)
    output[output > 1] = 1
    output[output < 0] = 0
    return output

def calculate_stats(masks):
    if masks.max() == 0:
        return pd.DataFrame(columns=['label', 'area', 'centroid_y', 'centroid_x'])

    stats = cc3d.statistics(masks)
    areas = stats['voxel_counts'][1:]
    centroids = stats['centroids'][1:]
    
    df = pd.DataFrame({
        'label': np.arange(1, len(areas)+1),
        'area': areas,
        'centroid_y': centroids[:,0],
        'centroid_x': centroids[:,1]
        })
    unique_labels = np.unique(masks)
    unique_labels = unique_labels[unique_labels != 0]
    if len(unique_labels) == len(areas):
        df['label'] = unique_labels

    return df

def save_results(masks, img_norm, df, output_base, suffix):
    output_tif_path = output_base + f"{suffix}.tif"
    output_npy_path = output_base + f"{suffix}.npy"
    output_csv_path = output_base + f"{suffix}.csv"
    output_png_path = output_base + f"{suffix}_qc.png"

    # 1. Save TIF
    print(f"Saving TIF: {output_tif_path}")
    io.imsave(output_tif_path, masks)

    # 2. Save NPY
    print(f"Saving NPY: {output_npy_path}")
    np.save(output_npy_path, masks)

    # 3. Save CSV
    print(f"Saving CSV: {output_csv_path}")
    df.to_csv(output_csv_path, index=False)

    # 4. Save QC PNG
    print(f"Saving QC image: {output_png_path}")
    plt.ioff()
    fig = plt.figure(figsize=(12, 12))
    plt.imshow(img_norm, cmap='gray')

    # Draw outlines
    if masks.max() > 0:
        outlines = plot.utils.outlines_list(masks)
        for o in outlines:
            plt.plot(o[:,0], o[:,1], color='r', linewidth=1)

    plt.axis('off')
    plt.title(f"Count: {len(df)} cells ({suffix})")
    plt.savefig(output_png_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

def run_segmentation_maxproj(dapi_path, output_base_path, diameter, no_gpu, threshold , model_type='nuclei'):
    # 1. Determine device
    use_gpu = not no_gpu and torch.cuda.is_available()
    device_name = "GPU" if use_gpu else "CPU"
    print(f"--- Starting 2D Max-Projection Segmentation on {device_name} ---")

    # 2. Read 3D DAPI stack
    print(f"Loading 3D DAPI stack: {dapi_path}")
    dapi_stack = io.imread(dapi_path) 

    print(f"Original shape: {dapi_stack.shape}")

    # 3. Max Projection to 2D
    if dapi_stack.ndim == 3:
        print("Performing Max Projection along Z-axis...")
        dapi_2d = np.max(dapi_stack, axis=0)
    elif dapi_stack.ndim == 2:
        print("Image is already 2D.")
        dapi_2d = dapi_stack
    else:
        raise ValueError(f"Unsupported image dimensions: {dapi_stack.ndim}")

    # 4. Normalize image
    print("Normalizing image...")
    dapi_2d_norm = percennorm(dapi_2d, 1, 99.8)
    # save normalized image for post check
    norm_output_path = output_base_path + "_norm.tif"
    print(f"Saving normalized image for post checking: {norm_output_path}")
    io.imsave(norm_output_path, dapi_2d_norm)

    # 5. Initialize Cellpose model
    print(f"Initializing Cellpose '{model_type}' model...")
    model = models.CellposeModel(gpu=use_gpu, model_type=model_type)

    # 6. Run segmentation(RAW)
    diam_arg = None if diameter == 0 else diameter
    print(f"Running 2D segmentation (Diameter={diameter if diameter>0 else 'Auto'})...")
    
    start_time = time.time()
    
    masks_raw, flows, styles = model.eval(
        dapi_2d_norm, 
        diameter=diam_arg, 
        channels=[0, 0],
        flow_threshold=0.4,
        cellprob_threshold=0.0,
        do_3D=False 
    )
    end_time = time.time()
    print(f"Segmentation finished in {end_time - start_time:.2f} seconds.")

    # --- PROCESS RAW DATA ---
    print("\nProcessing RAW data...")
    df_raw = calculate_stats(masks_raw)
    raw_total_area = df_raw['area'].sum()
    print(f"Raw detected cells: {len(df_raw)}")
    print(f"Overall area of raw dapi: {raw_total_area}")
    save_results(masks_raw, dapi_2d_norm, df_raw, output_base_path, suffix="_raw")


    # --- PROCESS FILTERED DATA ---
    print(f"\nProcessing FILTERED data (Threshold area >= {threshold})...")
    
    if len(df_raw) > 0:
        # Find labels that pass the threshold
        df_filtered = df_raw[df_raw['area'] >= threshold].copy()
        valid_labels = df_filtered['label'].values
        
        # Create a new mask with only valid labels
        masks_filtered = np.where(np.isin(masks_raw, valid_labels), masks_raw, 0)
        filtered_total_area = df_filtered['area'].sum()
        reduction_ratio = (1 - filtered_total_area / raw_total_area) * 100

        print(f"Overall area of filtered dapi: {filtered_total_area}")
        print(f"Area reduction ratio: {reduction_ratio:.2f}%")
        print(f"Filtered detected cells: {len(df_filtered)} (Removed {len(df_raw) - len(df_filtered)})")
    else:
        masks_filtered = np.zeros_like(masks_raw)
        df_filtered = pd.DataFrame(columns=['label', 'area', 'centroid_y', 'centroid_x'])
        print("No cells detected in raw data, skipping filtering logic.")

    save_results(masks_filtered, dapi_2d_norm, df_filtered, output_base_path, suffix="_filtered")
    print("\n--- Process completed successfully! ---")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run 2D Cellpose on Max Projected DAPI.")
    parser.add_argument('--input', type=str, required=True, help='Path to the 3D DAPI TIFF stack.')
    parser.add_argument('--output_base', type=str, required=True, help="Base path for outputs.")
    parser.add_argument('--diameter', type=float, default=0, help='Estimated NUCLEI diameter. 0 for auto.')
    parser.add_argument('--no-gpu', action='store_true', help='Disable GPU usage.')
    parser.add_argument('--threshold', type=int, default=100, required=True, help="Threshold of valid nuclear area") 
    args = parser.parse_args()
    
    run_segmentation_maxproj(args.input, args.output_base, args.diameter, args.no_gpu, args.threshold)

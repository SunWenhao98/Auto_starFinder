import argparse
import os
import numpy as np
import pandas as pd
import tifffile as tif
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

def parse_args():
    parser = argparse.ArgumentParser(description="Baysor QC Visualization (ClusterMap Style)")
    parser.add_argument('--dapi_path', required=True, help='Path to DAPI image')
    parser.add_argument('--mask_path', required=True, help='Path to Cellpose mask (.npy)')
    parser.add_argument('--baysor_csv', required=True, help='Path to segmentation.csv')
    parser.add_argument('--baysor_stats', required=True, help='Path to segmentation_cell_stats.csv')
    parser.add_argument('--output_dir', required=True, help='Output directory')
    parser.add_argument('--xy_scale', type=float, default=0.108, help='Microns per pixel')
    return parser.parse_args()

def main():
    args = parse_args()
    
    print(">>> Generating Baysor QC Plots (Matched Style)...")
    
    # ==========================================
    # 1. Load Images & Mask
    # ==========================================
    print(f"Loading DAPI: {args.dapi_path}")
    dapi = tif.imread(args.dapi_path)
    
    if dapi.ndim == 3:
        z_dim, h, w = dapi.shape
        dapi_max = np.max(dapi, axis=0)
        dapi_mid = dapi[z_dim // 2, :, :]
    else:
        h, w = dapi.shape
        dapi_max = dapi
        dapi_mid = dapi

    # Load Mask (.npy)
    print(f"Loading Mask: {args.mask_path}")
    try:
        mask = np.load(args.mask_path)
        if mask.ndim > 2:
            mask = np.max(mask, axis=0)
        binary_mask = (mask > 0).astype(int)
    except Exception as e:
        print(f"Warning: Could not load mask: {e}")
        binary_mask = np.zeros_like(dapi_max)

    # ==========================================
    # 2. Load Baysor Data
    # ==========================================
    print("Loading Baysor Data...")
    
    spots_x, spots_y, cell_int_ids = [], [], []
    center_x, center_y = [], []
    
    # A. Spots
    try:
        df_spots = pd.read_csv(args.baysor_csv)
        is_noise = df_spots['is_noise'].astype(str).str.lower() == 'true'
        df_cells = df_spots[~is_noise].copy()

        if len(df_cells) > 0:
            cell_codes, unique_ids = pd.factorize(df_cells['cell'])
            cell_int_ids = cell_codes + 1  # 1-based indexing for cmap

            spots_x = df_cells['x'].values / args.xy_scale
            spots_y = df_cells['y'].values / args.xy_scale
            
            print(f"  > Valid Spots: {len(spots_x)}")
            print(f"  > Unique Cells: {len(unique_ids)}")
        else:
            print("Warning: No valid cells found.")
            
    except Exception as e:
        print(f"Error loading spots: {e}")

    # B. Centroids
    try:
        df_stats = pd.read_csv(args.baysor_stats)
        center_x = df_stats['x'].values / args.xy_scale
        center_y = df_stats['y'].values / args.xy_scale
    except Exception as e:
        print(f"Error loading stats: {e}")

    # ==========================================
    # 3. Setup Colors
    # ==========================================
    if len(cell_int_ids) > 0:
        max_id = cell_int_ids.max()
        np.random.seed(42)
        cmap_vals = np.random.uniform(0.2, 1.0, size=(max_id + 1, 3))
        cmap_vals[0] = [0.1, 0.1, 0.1] 
    else:
        cmap_vals = None

    # ==========================================
    # 4. Plotting (2x2 Grid)
    # ==========================================
    fig, axes = plt.subplots(2, 2, figsize=(20, 20))

    step = 1 if len(spots_x) < 200000 else 5
    
    # --- Panel 1 (TL): DAPI Max Projection ---
    axes[0, 0].imshow(dapi_max, cmap='gray')
    axes[0, 0].set_title("DAPI (Max Projection)", fontsize=15)
    
    # --- Panel 2 (TR): DAPI Middle Slice ---
    axes[0, 1].imshow(dapi_mid, cmap='gray')
    axes[0, 1].set_title("DAPI (Layer {z_dim // 2})", fontsize=15)
    
    # --- Panel 3 (BL): DAPI + Spots + Centroids ---
    axes[1, 0].imshow(dapi_max, cmap='gray')
    
    if len(spots_x) > 0:
        axes[1, 0].scatter(spots_x[::step], spots_y[::step], 
                           c=cmap_vals[cell_int_ids[::step]], s=2, alpha=0.5)
        
    if len(center_x) > 0:
        axes[1, 0].scatter(center_x, center_y, c='red', s=20, marker='o', linewidth=0)
        
    axes[1, 0].set_title(f"DAPI + Baysor Result (Cells: {len(center_x)})", fontsize=15)
    
    # --- Panel 4 (BR): Binary Mask + Spots + Centroids ---
    axes[1, 1].imshow(binary_mask, cmap='gray') 
    
    if len(spots_x) > 0:
        axes[1, 1].scatter(spots_x[::step], spots_y[::step], 
                           c=cmap_vals[cell_int_ids[::step]], s=2, alpha=0.5)

    if len(center_x) > 0:
        axes[1, 1].scatter(center_x, center_y, c='red', s=20, marker='o', linewidth=0)
        
    axes[1, 1].set_title("Binary DAPI + Baysor Result", fontsize=15)

    # Standardize Axes
    for ax in axes.flat:
        ax.axis('off')
        ax.set_xlim(0, w)
        ax.set_ylim(h, 0)

    save_path = os.path.join(args.output_dir, "final_segmentation_results.png")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
    
    print(f"QC Dashboard saved to: {save_path}")

if __name__ == "__main__":
    main()
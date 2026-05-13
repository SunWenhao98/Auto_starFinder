import argparse
import os
import shutil
import numpy as np
import pandas as pd
import tifffile as tif
import scanpy as sc
import comseg
from comseg import dataset as ds
from comseg import dictionary
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

def parse_args():
    parser = argparse.ArgumentParser(description="Run ComSeg Pipeline for Single Sample")
    
    # I/O Paths
    parser.add_argument('--position_name', type=str, required=True, help='Sample/Position Name Identifier')
    parser.add_argument('--dapi_path', type=str, required=True, help='Path to DAPI image (for QC visualization)')
    parser.add_argument('--spots_path', type=str, required=True, help='Path to transcript spots CSV')
    parser.add_argument('--mask_path', type=str, required=True, help='Path to segmentation mask')
    parser.add_argument('--output_dir', type=str, required=True, help='Directory to save final results')
    parser.add_argument('--temp_dir', type=str, required=False, default=None, help='Directory for intermediate/temp files')
    
    # ComSeg Parameters
    parser.add_argument('--mean_cell_diameter', type=float, default=15.0, help='Expected mean cell diameter in microns')
    parser.add_argument('--max_cell_radius', type=float, default=15.0, help='Max radius for final RNA association')
    parser.add_argument('--scale_xy', type=float, default=0.108, help='Pixel size in microns (XY)')
    parser.add_argument('--scale_z', type=float, default=0.27, help='Pixel size in microns (Z)')
    parser.add_argument('--min_rna', type=int, default=30, help='Minimum RNAs required to keep a cell')
    parser.add_argument('--leiden_resolution', type=float, default=1.0, help='Resolution for Leiden clustering')
    parser.add_argument('--n_pcs', type=int, default=15, help='Number of PCs for neighbor calculation')
    parser.add_argument('--n_neighbors', type=int, default=20, help='Neighbors for clustering graph')
    parser.add_argument('--classify_neighbors', type=int, default=15, help='Neighbors for nuclei classification')
    parser.add_argument('--merge_corr', type=float, default=0.9, help='Correlation threshold to merge similar clusters')
    parser.add_argument('--commu_min', type=int, default=3, help='Min size of RNA community')
    
    return parser.parse_args()

def setup_temp_environment(args):
    temp_root = args.temp_dir
    temp_name = args.position_name
    path_dataset_folder = os.path.join(temp_root, "dataframes")
    path_to_mask_prior = os.path.join(temp_root, "mask")
    
    os.makedirs(path_dataset_folder, exist_ok=True)
    os.makedirs(path_to_mask_prior, exist_ok=True)
    
    print(f"--- Setting up intermediate environment in: {temp_root} ---")
    
    # --- 1. Process Spots CSV ---
    try:
        print(f"Processing CSV: {args.spots_path}")
        df = pd.read_csv(args.spots_path)
        col_map = {col: col.lower() for col in df.columns}
        df.rename(columns=col_map, inplace=True)

        if 'z' not in df.columns:
            df['z'] = 0

        required_cols = ['x', 'y', 'z', 'gene']
        df = df[required_cols]

        temp_csv_path = os.path.join(path_dataset_folder, f"{temp_name}.csv")
        df.to_csv(temp_csv_path, index=False)
        print(f"  -> Saved standardized CSV to: {temp_csv_path}")
        
    except Exception as e:
        raise ValueError(f"Error processing spots CSV: {e}")

    # --- 2. Process Segmentation Mask ---
    temp_mask_path = os.path.join(path_to_mask_prior, f"{temp_name}.tiff")
    
    try:
        print(f"Processing Mask: {args.mask_path}")
        mask_data = tif.imread(args.mask_path)
        tif.imwrite(temp_mask_path, mask_data)
        
        print(f"  -> Saved standardized Mask to: {temp_mask_path}")
        
    except Exception as e:
        print(f"Warning: Standard mask loading failed. Trying generic numpy load. Error: {e}")
        try:
            mask_data = np.load(args.mask_path)
            tif.imwrite(temp_mask_path, mask_data)
            print(f"  -> Saved standardized Mask (fallback) to: {temp_mask_path}")
        except:
            raise ValueError(f"Critical Error processing mask file: {e}")
            
    return temp_name, path_dataset_folder, path_to_mask_prior, temp_root, mask_data

def main():
    args = parse_args()
    
    # 1. Initialize Environment
    sample_name, path_dataset_folder, path_to_mask_prior, temp_root, mask_2d = setup_temp_environment(args)
    
    # 2. ComSeg Dataset Initialization
    print("\n--- Initializing ComSeg Dataset ---")
    dataset = ds.ComSegDataset(
        path_dataset_folder=path_dataset_folder,
        prior_name='in_nucleus',
        path_to_mask_prior=path_to_mask_prior,
        dict_scale={"x": args.scale_xy, 'y': args.scale_xy, "z": args.scale_z},
        mask_file_extension=".tiff",
        mean_cell_diameter=args.mean_cell_diameter
    )
    
    # 3. Add Prior Knowledge
    print("--- Adding Prior Knowledge from Mask ---")
    dataset.add_prior_from_mask(
        overwrite=True,
        compute_centroid=True
    )
    
    # 4. Compute Co-expression Correlation
    print("--- Computing Co-expression Graph ---")
    dataset.compute_edge_weight(
        images_subset=None,
        n_neighbors=args.n_neighbors,
        sampling=True,
        sampling_size=10000 
    )
    
    # 5. Graph Partitioning
    print("--- Graph Partitioning ---")
    Comsegdict = dictionary.ComSegDict(
        dataset=dataset,
        mean_cell_diameter=args.mean_cell_diameter,
        community_detection="with_prior"
    )
    Comsegdict.compute_community_vector()
    
    # 6. In Situ Clustering
    print("--- In Situ Clustering ---")
    safe_n_comps = max(args.n_pcs, 50)
    
    Comsegdict.compute_insitu_clustering(
        size_commu_min=args.commu_min,
        norm_vector=True,
        n_pcs=args.n_pcs,       
        n_comps=safe_n_comps,
        clustering_method="leiden",
        n_neighbors=args.n_neighbors,
        resolution=args.leiden_resolution,
        n_clusters_kmeans=4,
        palette=None,
        nb_min_cluster=0,
        min_merge_correlation=args.merge_corr
    )
    
    # Label the graph
    Comsegdict.add_cluster_id_to_graph(clustering_method="leiden_merged")
    
    # 7. Final RNA-Nuclei Association
    print("--- Final RNA-Nuclei Association ---")
    
    Comsegdict.classify_centroid(
        n_neighbors=args.classify_neighbors,
        dict_in_pixel=True,
        max_dist_centroid=None,
        key_pred="leiden_merged",
        distance="ngb_distance_weights"
    )
    
    Comsegdict.associate_rna2landmark(
        key_pred="leiden_merged",
        distance='distance',
        max_cell_radius=args.max_cell_radius
    )
    
    # 8. Export Results
    print("\n--- Exporting Results ---")
    
    adata, jsons = Comsegdict.anndata_from_comseg_result(
        return_polygon=False,
        alpha=0.6,
        min_rna_per_cell=args.min_rna
    )
    
    h5ad_path = os.path.join(args.output_dir, "result.h5ad")
    adata.write_h5ad(h5ad_path)
    print(f"Saved AnnData to: {h5ad_path}")
    
    try:
        # Extract Results
        output_df = Comsegdict.final_anndata.uns['df_spots'][sample_name].copy()
        
        # Save Raw Spot Assignment
        spots_out_path = os.path.join(args.output_dir, "final_spots_assignment.csv")
        output_df.to_csv(spots_out_path, index=True)
        print(f"Saved Spot Assignment to: {spots_out_path}")
        
        # --- Calculate Cell Centroids ---
        print("Calculating 3D Cell Centroids from allocated spots...")
        
        # Ensure column exists (Use cell_index_pred as key)
        if 'cell_index_pred' not in output_df.columns:
            raise KeyError("Critical: 'cell_index_pred' column missing from output!")

        all_spots = output_df.shape[0]
        valid_spots = output_df[output_df['cell_index_pred'] > 0]
        print(f"  -> Total Spots: {all_spots}, Valid Assigned Spots: {valid_spots.shape[0]}")

        centroids_3d = valid_spots.groupby('cell_index_pred')[['x', 'y', 'z']].mean().reset_index()
        centroids_3d.rename(columns={'cell_index_pred': 'cell_id'}, inplace=True)
        
        # Save Cell Centers CSV
        center_out_path = os.path.join(args.output_dir, "cell_center.csv")
        centroids_3d.to_csv(center_out_path, index=False)
        print(f"Saved 3D Cell Centers to: {center_out_path}")
        
    except Exception as e:
        print(f"Error processing output DataFrames: {e}")
        import traceback
        traceback.print_exc()
        output_df = pd.DataFrame()
        centroids_3d = pd.DataFrame()

    # 9. Cleanup
    if not args.temp_dir:
        try:
            shutil.rmtree(temp_root)
            print("Cleaned up temporary files.")
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")
    else:
        print(f"Intermediate files preserved.")

    # ================= QC PLOTTING BLOCK =================
    print("\n--- Generating QC Dashboard (ClusterMap Style) ---")
    try:
        # 1. Load DAPI
        dapi = tif.imread(args.dapi_path)
        img_z = 1
        if dapi.ndim == 3: 
            img_z = dapi.shape[0]
            dapi_max = np.max(dapi, axis=0) # Max Projection
            dapi_mid = dapi[img_z // 2, :, :] # Middle Slice
        else: 
            dapi_max = dapi
            dapi_mid = dapi
        
        # 2. Prepare Binary Mask (From Prior Mask)
        binary_mask_img = (mask_2d > 0).astype(int)

        # 3. Prepare Plot Data
        if not output_df.empty and 'cell_index_pred' in output_df.columns:
            spots_x = output_df['x'].values
            spots_y = output_df['y'].values
            # Use 'cell_index_pred' for coloring, 0 is background
            cell_ids = pd.to_numeric(output_df['cell_index_pred'], errors='coerce').fillna(0).astype(int).values
        else:
            print("Warning: Skipping spot plotting (dataframe empty or missing 'cell_index_pred').")
            spots_x, spots_y, cell_ids = [], [], []

        # 4. Create Color Map
        unique_cells = np.unique(cell_ids) if len(cell_ids) > 0 else np.array([0])
        np.random.seed(42)
        cmap_vals = np.random.rand(max(unique_cells.max(), 1000) + 1, 3)
        cmap_vals[0] = [0.8, 0.8, 0.8] # Grey for unassigned background

        # 5. Initialize Plot (2x2 Grid)
        fig, axes = plt.subplots(2, 2, figsize=(20, 20))
        
        # --- Panel 1 (TL): DAPI Max Projection ---
        axes[0, 0].imshow(dapi_max, cmap='gray')
        axes[0, 0].set_title('DAPI (Max Projection)', fontsize=15)
        
        # --- Panel 2 (TR): DAPI Middle Slice ---
        axes[0, 1].imshow(dapi_mid, cmap='gray')
        axes[0, 1].set_title(f'DAPI (Layer {img_z // 2})', fontsize=15)
        
        # --- Panel 3 (BL): DAPI Max + Colored Spots + Centroids ---
        axes[1, 0].imshow(dapi_max, cmap='gray')
        
        # Scatter only assigned spots to reduce clutter, or all with alpha
        if len(cell_ids) > 0:
            assigned_mask = cell_ids > 0
            if np.sum(assigned_mask) > 0:
                axes[1, 0].scatter(spots_x[assigned_mask], spots_y[assigned_mask], 
                                   c=cmap_vals[cell_ids[assigned_mask]], s=5, alpha=0.3)
        
        # Plot Centroids (Red)
        if not centroids_3d.empty:
            axes[1, 0].scatter(centroids_3d['x'], centroids_3d['y'], c='red', s=20)
            
        axes[1, 0].set_title(f'DAPI + ComSeg Result (Cells: {len(centroids_3d)})', fontsize=15)
        
        # --- Panel 4 (BR): Binary Mask + Colored Spots + Centroids ---
        axes[1, 1].imshow(binary_mask_img, cmap='gray')
        
        if len(cell_ids) > 0:
            assigned_mask = cell_ids > 0
            if np.sum(assigned_mask) > 0:
                axes[1, 1].scatter(spots_x[assigned_mask], spots_y[assigned_mask], 
                                   c=cmap_vals[cell_ids[assigned_mask]], s=5, alpha=0.3)
        
        if not centroids_3d.empty:
            axes[1, 1].scatter(centroids_3d['x'], centroids_3d['y'], c='red', s=20)
            
        axes[1, 1].set_title('Binary DAPI + ComSeg Result', fontsize=15)
        
        # Standardize Axes
        for ax in axes.flat:
            ax.axis('off')

        plt.tight_layout()
        qc_path = os.path.join(args.output_dir, 'final_segmentation_results.png')
        plt.savefig(qc_path, dpi=150)
        plt.close()
        print(f"QC Plot saved to: {qc_path}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"QC Plotting Warning: {e}")

    print(">>> ComSeg Pipeline Completed Successfully.")

if __name__ == "__main__":
    main()
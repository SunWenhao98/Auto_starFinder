

// run("Grid/Collection stitching", 
//     "type=[Grid: snake by rows] order=[Right & Down] grid_size_x=6 grid_size_y=6 tile_overlap=10 first_file_index_i=1 #设定拼接顺序、行数列数、重叠区域 directory=/gpfs/share/home/2300012257/starFinder_test/01_registration/IF/dapi file_names=Position{iii}.tif output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap computation_parameters=[Save computation time (but use more RAM)] image_output=[Fuse and display]");


// run("Grid/Collection stitching",
//     "type=[Grid: snake by rows] " +
//     "order=[Right & Down] " +
//     "grid_size_x=6 grid_size_y=6 " +
//     "tile_overlap=10 " +
//     "first_file_index_i=1 " +
//     "directory=/gpfs/share/home/2300012257/starFinder_test/01_registration/IF/dapi " +
//     "file_names=Position{iii}.tif " +
//     "output_textfile_name=TileConfiguration.txt " +
//     "fusion_method=[Linear Blending] " +
//     "regression_threshold=0.30 " +
//     "max/avg_displacement_threshold=2.50 " +
//     "absolute_displacement_threshold=3.50 " +
//     "compute_overlap " +
//     "computation_parameters=[Save computation time (but use more RAM)] " +
//     "image_output=[Fuse and display]"
// );





// ImageJ宏，拼接顺序规则，且FOV命名序号连续
print("Starting Grid/Collection stitching...");

args = getArgument();
arr = split(args, " ");
inputDir = arr[0];
gridX = arr[1];
gridY = arr[2];
first_index = arr[3];
outputName = arr[4];
stitchPattern = arr[5];

print("========================================")
print("inputDir = " + inputDir);
print("gridX = " + gridX);
print("gridY = " + gridY);
print("first_index = " + first_index);
print("outputName = " + outputName);
print("stitchPattern = " + stitchPattern);
print("=======================================")


if (stitchPattern == "Snake_row_Right_down") {
    stitchType = "Grid: snake by rows";
    stitchOrder = "Right & Down";

    // 构造参数
    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "grid_size_x=" + gridX + " " +
            "grid_size_y=" + gridY + " " +
            "tile_overlap=10 " +
            "first_file_index_i=" + first_index + " " +
            "directory=" + inputDir + " " +
            "file_names=Position{iii}.tif " +
            "output_textfile_name=TileConfiguration.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "compute_overlap " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";
    
    run("Grid/Collection stitching", params);

    saveAs("Tiff", inputDir + "/" + outputName + "_3dnew.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveAs("Tiff", inputDir + "/" + outputName + "_2dnew.tif");
    print("Finished Grid/Collection stitching.");
    close();
    close();


} else if (stitchPattern == "Positions_from_file") {
    stitchType = "Positions from file";
    stitchOrder = "Defined by TileConfiguration";

    // 构造参数
    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "directory=" + inputDir + " " +
            "layout_file=TileConfiguration.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "compute_overlap " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Write to disk] " +
            "output_directory=" + inputDir + " ";

    run("Grid/Collection stitching", params);

    // // 以获得 TileConfiguration.registered.txt 为运行目标
    // saveAs("Tiff", inputDir + "/" + outputName + "_3dnew.tif");
    // run("Z Project...", "projection=[Max Intensity]");
    // saveAs("Tiff", inputDir + "/" + outputName + "_2dnew.tif");
    print("Finished Grid/Collection stitching.");
    close();
    close();

    
} else if (stitchPattern == "Positions_from_file_p1") {
    stitchType = "Positions from file";
    stitchOrder = "Defined by TileConfiguration";

    // 构造参数
    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "directory=" + inputDir + " " +
            "layout_file=TileConfiguration.registered.p1.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);

    saveAs("Tiff", inputDir + "/" + outputName + "_3dnew_p1.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveAs("Tiff", inputDir + "/" + outputName + "_2dnew_p1.tif");
    print("Finished Grid/Collection stitching.");
    close();
    close();

} else if (stitchPattern == "Positions_from_file_p2") {
    stitchType = "Positions from file";
    stitchOrder = "Defined by TileConfiguration";

    // 构造参数
    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "directory=" + inputDir + " " +
            "layout_file=TileConfiguration.registered.p2.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);

    saveAs("Tiff", inputDir + "/" + outputName + "_3dnew_p2.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveAs("Tiff", inputDir + "/" + outputName + "_2dnew_p2.tif");
    print("Finished Grid/Collection stitching.");
    close();
    close();

} else if (stitchPattern == "Positions_from_file_downsampled") {

    print("Starting Stitching with downsampling...");
    stitchType = "Positions from file";
    stitchOrder = "Defined by TileConfiguration";

    var targetWidth = 1152;
    var targetHeight = 1152;

    // 构造参数
    // params = "type=[" + stitchType + "] " +
    //         "order=[" + stitchOrder + "] " +
    //         "directory=" + inputDir + " " +
    //         "layout_file=TileConfiguration.registered.txt " +
    //         "fusion_method=[Linear Blending] " +
    //         "regression_threshold=0.30 " +
    //         "max/avg_displacement_threshold=2.50 " +
    //         "absolute_displacement_threshold=3.50 " +
    //         "downsample_tiles " + 
    //         "width=" + targetWidth + " " +
    //         "height=" + targetHeight + " " +
    //         "interpolation=[Bicubic Interpolation] " +
    //         "subpixel_accuracy " +
    //         "computation_parameters=[Save memory (but be slower)] " +
    //         "image_output=[Fuse and display]";

    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "directory=" + inputDir + " " +
            "layout_file=TileConfiguration.registered.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "downsample_tiles " + 
            "x=0.5 " +      // 录制的缩放比例
            "y=0.5 " + 
            "width=" + targetWidth + " " +
            "height=" + targetHeight + " " + 
            "interpolation=Bicubic " +
            "average " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);

    saveAs("Tiff", inputDir + "/" + outputName + "_3d_bin2.tiff");
    run("Z Project...", "projection=[Max Intensity]");
    saveAs("Tiff", inputDir + "/" + outputName + "_2d_bin2.tif");
    print("Finished Grid/Collection stitching.");
    close();
    close();

} else if (stitchPattern == "Positions_from_file_MIP") {
    stitchType = "Positions from file";
    stitchOrder = "Defined by TileConfiguration";

    // 构造参数
    params = "type=[" + stitchType + "] " +
            "order=[" + stitchOrder + "] " +
            "directory=" + inputDir + " " +
            "layout_file=TileConfiguration.registered.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);

    saveAs("Tiff", inputDir + "/" + outputName + "_refDAPI_MIP.tif");

    print("Finished Grid/Collection stitching.");
    close();
    close();

}
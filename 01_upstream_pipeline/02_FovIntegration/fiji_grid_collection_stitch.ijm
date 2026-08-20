print("Starting Grid/Collection stitching...");

inputDir = "";
gridX = "";
gridY = "";
firstIndex = "";
outputName = "";
stitchPattern = "";
layoutFile = "";
outputTextfileName = "";
regressionThreshold = "";
maxAvgDisplacementThreshold = "";
absoluteDisplacementThreshold = "";
fusionMethod = "";
computeOverlap = "";
subpixelAccuracy = "";
computationParameters = "";
imageOutput = "";
outputDirectory = "";
saveFormat = "";

records = split(getArgument(), ";");
for (recordIndex = 0; recordIndex < records.length; recordIndex++) {
    separatorIndex = indexOf(records[recordIndex], "=");
    if (separatorIndex < 1)
        exit("Invalid macro argument record: " + records[recordIndex]);
    key = substring(records[recordIndex], 0, separatorIndex);
    value = substring(records[recordIndex], separatorIndex + 1);

    if (key == "input_dir") inputDir = value;
    else if (key == "grid_x") gridX = value;
    else if (key == "grid_y") gridY = value;
    else if (key == "first_index") firstIndex = value;
    else if (key == "output_name") outputName = value;
    else if (key == "stitch_pattern") stitchPattern = value;
    else if (key == "layout_file") layoutFile = value;
    else if (key == "output_textfile_name") outputTextfileName = value;
    else if (key == "regression_threshold") regressionThreshold = value;
    else if (key == "max_avg_displacement_threshold") maxAvgDisplacementThreshold = value;
    else if (key == "absolute_displacement_threshold") absoluteDisplacementThreshold = value;
    else if (key == "fusion_method") fusionMethod = value;
    else if (key == "compute_overlap") computeOverlap = value;
    else if (key == "subpixel_accuracy") subpixelAccuracy = value;
    else if (key == "computation_parameters") computationParameters = value;
    else if (key == "image_output") imageOutput = value;
    else if (key == "output_directory") outputDirectory = value;
    else if (key == "save_format") saveFormat = value;
    else exit("Unknown macro argument key: " + key);
}

requiredValues = newArray(
    inputDir, gridX, gridY, firstIndex, outputName, stitchPattern,
    layoutFile, outputTextfileName, regressionThreshold,
    maxAvgDisplacementThreshold, absoluteDisplacementThreshold,
    fusionMethod, computeOverlap, subpixelAccuracy,
    computationParameters, imageOutput, outputDirectory, saveFormat
);
requiredNames = newArray(
    "input_dir", "grid_x", "grid_y", "first_index", "output_name", "stitch_pattern",
    "layout_file", "output_textfile_name", "regression_threshold",
    "max_avg_displacement_threshold", "absolute_displacement_threshold",
    "fusion_method", "compute_overlap", "subpixel_accuracy",
    "computation_parameters", "image_output", "output_directory", "save_format"
);
for (requiredIndex = 0; requiredIndex < requiredValues.length; requiredIndex++) {
    if (requiredValues[requiredIndex] == "")
        exit("Missing required macro argument: " + requiredNames[requiredIndex]);
}

computeOverlapOption = booleanOption(computeOverlap, "compute_overlap");
subpixelAccuracyOption = booleanOption(subpixelAccuracy, "subpixel_accuracy");
if (saveFormat != "tiff" && saveFormat != "ome_tiff" && saveFormat != "ome_bigtiff")
    exit("Unknown save_format: " + saveFormat);

print("inputDir = " + inputDir);
print("outputName = " + outputName);
print("stitchPattern = " + stitchPattern);
print("layoutFile = " + layoutFile);
print("saveFormat = " + saveFormat);

if (stitchPattern == "Snake_row_Right_down") {
    params = "type=[Grid: snake by rows] " +
            "order=[Right & Down] " +
            "grid_size_x=" + gridX + " " +
            "grid_size_y=" + gridY + " " +
            "tile_overlap=10 " +
            "first_file_index_i=" + firstIndex + " " +
            "directory=[" + inputDir + "] " +
            "file_names=Position{iii}.tif " +
            "output_textfile_name=" + outputTextfileName + " " +
            "fusion_method=[" + fusionMethod + "] " +
            "regression_threshold=" + regressionThreshold + " " +
            "max/avg_displacement_threshold=" + maxAvgDisplacementThreshold + " " +
            "absolute_displacement_threshold=" + absoluteDisplacementThreshold + " " +
            computeOverlapOption +
            subpixelAccuracyOption +
            "computation_parameters=[" + computationParameters + "] " +
            "image_output=[" + imageOutput + "]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3dnew.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else if (stitchPattern == "Positions_from_file") {
    params = "type=[Positions from file] " +
            "order=[Defined by TileConfiguration] " +
            "directory=[" + inputDir + "] " +
            "layout_file=" + layoutFile + " " +
            "fusion_method=[" + fusionMethod + "] " +
            "regression_threshold=" + regressionThreshold + " " +
            "max/avg_displacement_threshold=" + maxAvgDisplacementThreshold + " " +
            "absolute_displacement_threshold=" + absoluteDisplacementThreshold + " " +
            computeOverlapOption +
            subpixelAccuracyOption +
            "computation_parameters=[" + computationParameters + "] " +
            "image_output=[" + imageOutput + "] " +
            "output_directory=[" + outputDirectory + "]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3dnew.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else if (stitchPattern == "Positions_from_file_p1") {
    params = "type=[Positions from file] " +
            "order=[Defined by TileConfiguration] " +
            "directory=[" + inputDir + "] " +
            "layout_file=TileConfiguration.registered.p1.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3dnew_p1.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else if (stitchPattern == "Positions_from_file_p2") {
    params = "type=[Positions from file] " +
            "order=[Defined by TileConfiguration] " +
            "directory=[" + inputDir + "] " +
            "layout_file=TileConfiguration.registered.p2.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "subpixel_accuracy " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3dnew_p2.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else if (stitchPattern == "Positions_from_file_downsampled") {
    targetWidth = 1152;
    targetHeight = 1152;
    params = "type=[Positions from file] " +
            "order=[Defined by TileConfiguration] " +
            "directory=[" + inputDir + "] " +
            "layout_file=TileConfiguration.registered.txt " +
            "fusion_method=[Linear Blending] " +
            "regression_threshold=0.30 " +
            "max/avg_displacement_threshold=2.50 " +
            "absolute_displacement_threshold=3.50 " +
            "downsample_tiles x=0.5 y=0.5 " +
            "width=" + targetWidth + " height=" + targetHeight + " " +
            "interpolation=Bicubic average " +
            "computation_parameters=[Save memory (but be slower)] " +
            "image_output=[Fuse and display]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3d_bin2.tiff");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else if (stitchPattern == "Positions_from_file_mosaic") {
    mosaicSubpixelAccuracyOption = booleanOption(subpixelAccuracy, "subpixel_accuracy");
    params = "type=[Positions from file] " +
            "order=[Defined by TileConfiguration] " +
            "directory=[" + inputDir + "] " +
            "layout_file=" + layoutFile + " " +
            "fusion_method=[" + fusionMethod + "] " +
            mosaicSubpixelAccuracyOption +
            "image_output=[" + imageOutput + "]";

    run("Grid/Collection stitching", params);
    // saveAs("Tiff", inputDir + "/" + outputName + "_3d_Fiji.tif");
    run("Z Project...", "projection=[Max Intensity]");
    saveProjection(outputDirectory, outputName, saveFormat);

} else {
    exit("Unknown stitch_pattern: " + stitchPattern);
}

function booleanOption(value, optionName) {
    if (value == "true") return optionName + " ";
    if (value == "false") return "";
    exit("Expected true/false for " + optionName + ", got: " + value);
}

function saveProjection(directory, name, format) {
    if (format == "tiff") {
        outputPath = directory + "/" + name + "_2d_Fiji.tif";
        saveAs("Tiff", outputPath);
        print("Saved 2D projection: " + outputPath);
    } else if (format == "ome_tiff") {
        outputPath = directory + "/" + name + "_2d_Fiji.ome.tif";
        print("OME export delegated to BeanShell bridge: " + outputPath);
    } else if (format == "ome_bigtiff") {
        outputPath = directory + "/" + name + "_2d_Fiji.ome.btf";
        // Bio-Formats also recognizes .ome.tf8 for OME-BigTIFF.
        print("OME export delegated to BeanShell bridge: " + outputPath);
    } else {
        exit("Unknown save_format: " + format + ". Expected tiff, ome_tiff, or ome_bigtiff (.ome.btf/.ome.tf8).");
    }
}

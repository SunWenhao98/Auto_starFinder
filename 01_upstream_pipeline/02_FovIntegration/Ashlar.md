整体逻辑
这组脚本围绕一个核心思想：先用一个可靠通道算出拼接坐标，再复用这些坐标去拼其它通道。
最主要的数据流是：
已有 TileConfiguration.txt
  -> p22_ashlar_stitching.py
  -> TileConfiguration.registered.txt
  -> p24_ashlar_stitch_mosaic.py
  -> 其它 IF channel stitched image
如果要处理 IF raw 或 TE extra channels，则加上：
IF registration shift logs
  -> p23_prepare_if_raw_tileconfig.py
  -> TileConfigurationIF.txt + IF_raw channel layout
  -> p24_ashlar_stitch_mosaic.py

raw round011 / TE channels
  -> p21_prepare_noRef_layout.py
  -> TE-DAPI / TE-nt / TE-rb channel layout
  -> p24_ashlar_stitch_mosaic.py
  -> p27_make_TE_rgb.py
  
p22_ashlar_stitching.py
这个脚本是“坐标校正 + 首轮 Ashlar 拼接”的核心。
它读取：
--input_dir
--config_file
其中 config_file 是 TileConfiguration.txt 风格文件，里面有每个 tile 的初始坐标。
它内部定义了 TiffTxtReader，这个 reader 把 TileConfiguration.txt 转成 Ashlar 需要的 metadata：
filename
x/y 坐标
tile size
pixel dtype
z depth
pixel_size
然后它用第一张图判断图像维度。如果输入是 3D stack，它可以按三种模式读取：
mip    对 z 轴做 max projection
stack  按 z slice 作为 Ashlar channel 输出 3D
slice  只取指定 z slice
主流程分四步：
1. 用 TiffTxtReader(..., mode="mip") 读 MIP 图。
2. 用 EdgeAligner 根据图像内容估计 tile 之间的真实错位。
3. 写出：
*_coordinates.csv
*_edge_alignment.csv
TileConfiguration.registered.txt
4. 用 Ashlar Mosaic + PyramidWriter 输出 stitched OME-TIFF。
这个脚本适合的场景是：你有初始 TileConfiguration.txt，但希望用图像内容进一步优化 tile 间相对位置。通常应先用 DAPI / ref-DAPI / ref-DAPI_MIP 这种结构清晰、跨 tile 相关性强的通道跑它。
p24_ashlar_stitch_mosaic.py
这个脚本是“复用坐标，直接拼接”的脚本。
它不再跑 EdgeAligner，也就是说它不重新估计 tile 间 shift。它读取已经存在的：
TileConfiguration.registered.txt
然后直接按里面的坐标生成 mosaic。
它内部有两个关键结构：
TiffDirectReader
DirectAligner
TiffDirectReader 负责读取 config 和图像。DirectAligner 是一个轻量对象，只提供 Ashlar Mosaic 需要的坐标、origin、mosaic_shape 等属性。
这个脚本适合的场景是：你已经用 p22 在 DAPI 上得到可靠 registered 坐标，现在要把同一套坐标应用到其它通道，例如：
488-CD144
561-CA9
647-CD31
TE-nt
TE-rb
它还有 --channel_from 和 --channel_to。这用于把 config 里的文件路径从一个通道替换到另一个通道。例如 config 里是 DAPI 路径，但你要拼 488-CD144，就可以替换路径 token，而不需要重新生成坐标文件。
p23_prepare_if_raw_tileconfig.py
这个脚本是为“raw IF channel 复用 registered 坐标”做准备。
它假设 ref-DAPI 的 mosaic 坐标已经有了：
IF_DIR/TileConfiguration.registered.txt
同时 IF registration 过程中，每个 Position 的 shift 已经记录在：
registration_dir/PositionXXX/log/log_protein_registration.txt
它做三件事：
1. 复制 ref 坐标：
TileConfiguration.registered.txt -> TileConfigurationRef.txt
2. 从 raw IF 目录提取每个 Position 的多通道 tif，整理成：
IF_raw/488-CD144/Position001.tif
IF_raw/561-CA9/Position001.tif
IF_raw/647-CD31/Position001.tif
IF_raw/DAPI/Position001.tif
3. 把 IF registration shift 加到 ref 坐标上，写：
TileConfigurationIF.txt
if_registration_shifts.csv
这里最关键的函数是 transform_shift()。如果 downstream stitching 会对 FOV 做 rotate90，它把 registration shift 从原始 [row, col] 转成旋转后的 [y, x] = [col, -row]。如果不旋转，就保持 [y, x] = [row, col]。
这个脚本适合的场景是：IF raw 图像没有直接处在 ref-DAPI 坐标系里，但你有 IF registration 产生的 per-FOV shift，需要把这些 shift 叠加到 registered 坐标上，再拼 raw IF channel。
p21_prepare_noRef_layout.py
这个脚本是为 TE / extra channels 整理输入目录的。
它读取类似：
round011/Position001/*_ch03.tif
round011/Position001/*_ch00.tif
round011/Position001/*_ch01.tif
然后按 --channels 参数映射到输出 channel 目录。默认映射是：
ch03 -> TE-DAPI
ch00 -> TE-nt
ch01 -> TE-rb
输出类似：
output_dir/TE-DAPI/Position001.tif
output_dir/TE-nt/Position001.tif
output_dir/TE-rb/Position001.tif
extra_layout_manifest.csv
它只负责“整理文件布局”，不生成坐标、不做 stitching。它可以用 symlink、hardlink、copy，或者在指定 --output_format 时转换成 uint8/uint16。
适用场景是：TE 或其它 extra round 的原始数据仍按 PositionXXX 分散保存，需要整理成 p24_ashlar_stitch_mosaic.py 更容易读取的 channel-folder 结构。
p27_make_TE_rgb.py
这个脚本是最后的展示/合成工具。
它读取两张已经 stitched 好的 2D 图：
--red_image    通常 TE-nt
--green_image  通常 TE-rb
然后生成一个 RGB OME-TIFF：
R = red_image
G = green_image
B = 0
如果加 --rescale_to_uint8，它会按 percentile 把两张图拉伸到 uint8，默认范围是 0 到 99.9 percentile。
它适合的场景是：TE-nt 和 TE-rb 已经分别 stitch 完成，现在想快速生成一张红绿合成图，用于 visual check 或汇报展示。
它们之间的工作场景区别
如果你是第一次为某个 IF batch 建立可靠拼接坐标，用：
p22_ashlar_stitching.py
如果你已经有 TileConfiguration.registered.txt，只是要拼其它同坐标系通道，用：
p24_ashlar_stitch_mosaic.py
如果你要把 IF registration 的 per-FOV shift 叠加到 raw IF channel 上，先用：
p23_prepare_if_raw_tileconfig.py
然后通常再接：
p24_ashlar_stitch_mosaic.py
如果你要整理 TE / extra round 的 channel 文件结构，先用：
p21_prepare_noRef_layout.py
然后通常再接：
p24_ashlar_stitch_mosaic.py
如果你已经有 TE-nt 和 TE-rb 的 stitched 结果，想合成红绿图，用：
p27_make_TE_rgb.py
一句话：p22 负责“算坐标并拼 ref”，p24 负责“复用坐标拼其它通道”，p23 负责“把 IF raw 和 registration shift 接入这个坐标体系”，p26 负责“把 TE raw 文件整理成可拼接布局”，p27 负责“把 TE stitched 结果合成 RGB”。

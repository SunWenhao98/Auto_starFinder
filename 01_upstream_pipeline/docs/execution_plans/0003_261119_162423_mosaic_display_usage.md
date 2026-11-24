# 33 Per-round MIP Display Preparation

`33_prepare_mosaic_display.sh` 将同一轮已经拼接的单通道二维 MIP，打包为多通道金字塔 OME-BigTIFF，并按 profile 保存 RGB 叠加 PNG。IF 和 seqE 分别调用现有入口；不增加新的批量接口。

## 输入与输出口径

- IF：561-CA9、488-CD144、647-CD31、DAPI，共四通道。
- seqE：647-GCnt、561-GTrb、DAPI，共三通道。原始 ch02=Padlayer 供解码占位，11a panel 保持四项；拼接、29 清单及 33 不列入 Padlayer。
- 每轮内部的像素大小、尺寸、原点、方向和 FOV 布局须一致。IF 与 seqE 可以使用不同 XY 尺寸，分别生成各自的 OME/PNG。
- 本批只要求二维 MIP 叠加，OME 的 C 轴表示通道，SizeZ=SizeT=1。参考 DAPI 单独保留，不强制与两轮打包。完整三维叠加和 Z 位移补偿不在本批范围。
- 33 直接读取现成的二维文件，不自行配准或从原始堆栈计算 MIP。通用工具仍支持显式提供的二维 Z 平面，本批清单只列 mip。

A 路线沿用每轮自然画布，无需为了展示额外统一跨轮画布。B 使用 29 的既有输出，C 使用 32 的既有输出。33 仅核对同一次调用中图像的尺寸，空间匹配由本轮上游出图过程保证。

## 每轮一份输入清单

清单中的路径相对 JSON 所在目录，也可用绝对路径。输入键的顺序决定 OME-TIFF 的 C 轴。

`display_IF_inputs.json`：

```json
{
  "pixel_size_um": 0.142,
  "planes": {
    "mip": {
      "IF_CA9": "stitching_results/IF_561-CA9_2d.ome.tif",
      "IF_CD144": "stitching_results/IF_488-CD144_2d.ome.tif",
      "IF_CD31": "stitching_results/IF_647-CD31_2d.ome.tif",
      "IF_DAPI": "stitching_results/IF_DAPI_2d.ome.tif"
    }
  }
}
```

`display_seqE_inputs.json`：

```json
{
  "pixel_size_um": 0.142,
  "planes": {
    "mip": {
      "seqE_GCnt": "stitching_results/seqE_647-GCnt_2d.ome.tif",
      "seqE_GTrb": "stitching_results/seqE_561-GTrb_2d.ome.tif",
      "seqE_DAPI": "stitching_results/seqE_DAPI_2d.ome.tif"
    }
  }
}
```

示例前缀来自 24；Fiji、B 的 29 或 C 的 32 使用各自实际输出路径。不要仅替换文件扩展名或混用不同方法、不同轮次的画布。

## 每轮一份展示 profile

IF 示例 `display_IF_profile.json`：

```json
{
  "channels": {
    "IF_CA9": {"color": [230, 159, 0]},
    "IF_CD144": {"color": [0, 158, 115]},
    "IF_CD31": {"color": [204, 121, 167]},
    "IF_DAPI": {"color": [86, 180, 233]}
  },
  "overlays": {
    "all": ["IF_CA9", "IF_CD144", "IF_CD31", "IF_DAPI"],
    "DAPI and CA9": ["IF_DAPI", "IF_CA9"]
  }
}
```

seqE 示例 `display_seqE_profile.json`：

```json
{
  "channels": {
    "seqE_GCnt": {"color": [230, 159, 0]},
    "seqE_GTrb": {"color": [204, 121, 167]},
    "seqE_DAPI": {"color": [86, 180, 233]}
  },
  "overlays": {
    "all": ["seqE_GCnt", "seqE_GTrb", "seqE_DAPI"],
    "translation": ["seqE_GCnt", "seqE_GTrb"]
  }
}
```

需要调整亮度时，在通道设置中提供 `limits: [lo, hi]`；缺省使用该通道原 dtype 的完整范围。需要扣背景时，提供正的 `background_radius_px`。比较同一样本、同通道的不同方法时复用同一套显示参数。

## 配置与生成

以下片段合并到完整 `batch_config.upstream.ini`。同一样本、方法的两轮使用不同 job_suffix、清单、profile 和输出目录。仅展示时 JOB 只启用 33；B 若需同时应用变换，可在各自 JOB 中先启用 29。

```ini
[JOB_DISPLAY_IF]
project_name = SAMPLE
regDir_suffix = _NEW_SAMPLE
job_suffix = _SAMPLE_IF_mip
run_mosaic_display = true
mosaic_display_stitching_workdir = A_Ashlar
mosaic_display_input_manifest = display_IF_inputs.json
mosaic_display_profile = display_IF_profile.json
mosaic_display_output_dirname = display_review/IF

[JOB_DISPLAY_SEQE]
project_name = SAMPLE
regDir_suffix = _NEW_SAMPLE
job_suffix = _SAMPLE_seqE_mip
run_mosaic_display = true
mosaic_display_stitching_workdir = A_Ashlar
mosaic_display_input_manifest = display_seqE_inputs.json
mosaic_display_profile = display_seqE_profile.json
mosaic_display_output_dirname = display_review/seqE
```

generator 每个 JOB 每个步骤调用一次，使用现有顺序与依赖生成两个独立展示任务，不自动强迫两轮图像同尺寸。目录和文件路径相对于该方法 workdir，输出目录每次使用新名称。

## 两个开关与交付

- `subtract_background` 与 `apply_display_mapping` 独立控制，默认均关闭。
- 背景扣除使用 white top-hat，方形窗口边长为 `2 × radius_px + 1`，会改变本次展示版 OME 像素。它与 Fiji rolling ball 不属于相同参数定义；先在代表区域选定参数。
- 显示映射控制 profile 中的颜色和亮度范围，用于 PNG 与显示预设，不改 OME 灰度值。关闭时使用中性灰度和原 dtype 范围。
- 每轮输出 `mip.ome.tif`，完整分辨率保留有效灰度精度。混合 uint8/uint16 时按原数值存为 uint16。
- 每个叠加组合输出 8-bit RGB PNG，长边不超过 2048；小图保持原尺寸。PNG 用于 VS Code 快速查看，原尺寸细节保留在 OME 最高分辨率层。

```text
<method>/display_review/
  IF/
    mip.ome.tif
    mip_01_all.png
    mip_02_DAPI-and-CA9.png
    display_presets.json
  seqE/
    mip.ome.tif
    mip_01_all.png
    mip_02_translation.png
    display_presets.json
```

`display_presets.json` 按平面记录图像名、通道顺序和各叠加组合，并在 `png_preview` 中记录 PNG 文件名、尺寸和来源金字塔层。Viv 集成可将预设直接作为图层选项使用。示例中的 `presetUrl` 为已授权文件服务上的 JSON 地址。

```js
import { loadOmeTiff, MultiscaleImageLayer } from '@hms-dbmi/viv';

const review = await fetch(presetUrl).then(response => response.json());
const plane = review.planes.mip;
const imageUrl = new URL(plane.image, presetUrl).href;
const { data: loader } = await loadOmeTiff(imageUrl);
const layer = new MultiscaleImageLayer({
  id: 'mip-review',
  loader,
  ...plane.overlays['DAPI and CA9'],
});
```

独立的 Avivator 可打开 OME-TIFF。自动套用 JSON 组合由 Viv 图层集成完成。远程读取 TIFF 需支持 HTTP Range，跨域时还需相应 CORS 配置。项目图像可在已有授权的私有文件服务提供。参见 [Viv 的 OME-TIFF 查看说明](https://github.com/hms-dbmi/viv/blob/main/sites/docs/tutorial/README.md)。

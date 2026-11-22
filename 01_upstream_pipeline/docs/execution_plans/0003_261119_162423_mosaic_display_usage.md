# 33 Mosaic Display Preparation

`33_prepare_mosaic_display.sh` 读取 A／B／C 已经对齐的单通道 MIP 或指定 Z 切片，可选扣除背景，再按平面保存多通道金字塔 OME-BigTIFF 和可在 VS Code 直接打开的 PNG 预览。颜色、亮度范围和叠加组合由 `display_presets.json` 提供。

## 输入和启用方式

每份输入清单对应某个样本、参考轮和路线。清单中的每一组图必须来自同一个 XY 画布，包括像素尺寸、方向、原点和覆盖范围。33 会检查每组图的 XY 尺寸，但是否同一画布由上游配准与出图过程确定。先对齐，再打包。方案 B 先由 29 把 IF 与 seqE 的图分别对齐到同一 ref 画布，然后在清单里引用其输出。方案 C 可直接引用 32 同一批的图。方案 A 需使用统一画布出图。跨路线联动查看还需共同的展示坐标或已知的坐标映射。

`display_inputs.json` 中的路径相对该 JSON 所在目录，也可写绝对路径。每个键代表一张已经输出的 2D 平面。以下是两通道例子，正式审阅可按同一结构列出全部九个通道。清单中的通道顺序决定 OME-TIFF 的 C 轴。

```json
{
  "pixel_size_um": 0.142,
  "planes": {
    "mip": {
      "ref_DAPI": "stitching_results/stitched_joint_refDAPI_2d.ome.tif",
      "IF_CA9": "stitching_results/stitched_joint_561-CA9_2d.ome.tif"
    },
    "z020": {
      "ref_DAPI": "stitching_results/stitched_joint_refDAPI_z020_2d.ome.tif",
      "IF_CA9": "stitching_results/stitched_joint_561-CA9_z020_2d.ome.tif"
    }
  }
}
```

`z020` 在例子中表示上游导出的第 20 层。33 直接读取列出的二维文件。不同轮次若起始 Z 或层间距不同，选层须按实际物理深度对应。当前 Fiji 拼接输出以 MIP 为主，Fiji 分支需要提供已经按同一几何导出的 Z 切片才可列入。

`display_profile.json` 定义每通道的背景参数和显示设置。此处数值仅演示接口。

```json
{
  "channels": {
    "ref_DAPI": {"color": [86, 180, 233], "limits": [100, 18000]},
    "IF_CA9": {
      "background_radius_px": 60,
      "color": [230, 159, 0],
      "limits": [20, 5000]
    }
  },
  "overlays": {
    "DAPI": ["ref_DAPI"],
    "DAPI and CA9": ["ref_DAPI", "IF_CA9"]
  },
  "planes": {
    "z020": {
      "channels": {"IF_CA9": {"background_radius_px": 45, "limits": [20, 2800]}}
    }
  }
}
```

`planes` 可省略。某平面的 `channels` 按通道覆盖指定字段。该平面也可显式用自己的 `overlays` 替换全局组合，尤其是缺少某通道的分支。比较同一样本、同通道、同类图像时复用同一 profile，避免各图独立拉伸导致强度看起来不同。

在完整 `batch_config.upstream.ini` 中启用 33。以下字段相对于样本的 `02_registration<suffix>/stitching_workdir` 组织。

```ini
run_mosaic_display = true
mosaic_display_stitching_workdir = stitching_joint_compare
mosaic_display_input_manifest = display_inputs.json
mosaic_display_profile = display_profile.json
mosaic_display_output_dirname = display_background_v01
mosaic_display_subtract_background = true
mosaic_display_apply_display_mapping = true
```

单独运行时只启用 33。在同一个 JOB 中与上游步骤一起启用时，generator 会将 33 接在该 JOB 的前一步成功之后。33 也可用具名参数直接调用 `p33_prepare_mosaic_display.py`，运行环境为 `ashlar`。输出目录每次指定新名称。

## 两个开关与输出

- `subtract_background` 开启时，只有 `background_radius_px` 为正的通道执行 white top-hat。方形窗口边长为 `2 × radius_px + 1`，逐块计算使用足够的重叠边界。较宽的弱信号也可能被扣除，先在代表性区域核对。实现基于 [SciPy white top-hat](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.white_tophat.html)，与 Fiji rolling ball 的参数和像素结果不可直接互换。
- `apply_display_mapping` 开启时，网页和 PNG 预览使用 profile 里的颜色和亮度上下限。关闭时使用中性灰度和通道原 dtype 的范围。叠加组合在两种状态下均可使用。
- 每个平面输出一份 `<plane>.ome.tif`。完整分辨率保留通道轴和有效灰度精度，混合 uint8／uint16 时按原数值统一存为 uint16。低分辨率层供缩放浏览。背景处理可关闭，另存一版时可从查看器切换处理前后两个文件。
- 每个平面的每组叠加输出一张 8 位 RGB PNG，例如 `mip_02_DAPI-and-CA9.png`。PNG 从本次 OME-TIFF 中长边不超过 2048 像素的最高分辨率层生成，小图使用原尺寸。各通道按显示范围映射后按颜色相加，输出限幅到 0–255。VS Code 可直接打开，后续像素级核对使用 OME-TIFF。

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

from functools import partial
import vapoursynth as vs
from vapoursynth import core

from .base import Depth

from typing import List, Union, Optional

from rekt import rektlvls, rekt_fast
from vsutil import scale_value, plane


def LumaMaskMerge(clipa: vs.VideoNode,
                  clipb: vs.VideoNode,
                  threshold: Optional[Union[int, float]] = None,
                  invert: bool = False,
                  scale_inputs: bool = False,
                  planes: Union[int, List[int]] = 0) -> vs.VideoNode:
    """
    LumaMaskMerge, merges clips using a binary mask defined by a brightness level.
    > Usage: LumaMaskMerge(clipa, clipb, threshold, invert, scale_inputs)
      * threshold is the brightness level. clipb is applied where the brightness is below threshold
      * If invert = True, clipb is applied where the brightness is above threshold
      * scale_inputs = True scales threshold from 8bits to current bit depth.
      * Use planes to specify which planes should be merged from clipb into clipa. Default is first plane.
    """
    p = (1 << clipa.format.bits_per_sample) - 1

    if scale_inputs and threshold is not None:
        threshold = scale_value(threshold, 8, clipa.format.bits_per_sample)
    elif threshold is None:
        threshold = (p + 1) / 2

    if not invert:
        mask = core.std.Binarize(clip=clipa.std.ShufflePlanes(0, vs.GRAY), threshold=threshold, v0=p, v1=0)
    else:
        mask = core.std.Binarize(clip=clipa.std.ShufflePlanes(0, vs.GRAY), threshold=threshold, v0=0, v1=p)

    return core.std.MaskedMerge(clipa=clipa, clipb=clipb, mask=mask, planes=planes)


def RGBMaskMerge(clipa: vs.VideoNode,
                 clipb: vs.VideoNode,
                 Rmin: int,
                 Rmax: int,
                 Gmin: int,
                 Gmax: int,
                 Bmin: int,
                 Bmax: int,
                 scale_inputs: bool = False) -> vs.VideoNode:
    """
    RGBMaskMerge, merges clips using a binary mask defined by a RGB range.
    > Usage: RGBMaskMerge(clipa, clipb, Rmin, Rmax, Gmin, Gmax, Bmin, Bmax, scale_inputs)
      * clipb is applied where Rmin < R < Rmax and Gmin < G < Gmax and Bmin < B < Bmax
      * scale_inputs = True scales Rmin, Rmax, Gmin, Gmax, Bmin, Bmax from 8bits to current bit depth (8, 10 or 16).
    """
    p = (1 << clipa.format.bits_per_sample) - 1

    if scale_inputs:
        Rmin = scale_value(Rmin, 8, clipa.format.bits_per_sample)
        Rmax = scale_value(Rmax, 8, clipa.format.bits_per_sample)
        Gmin = scale_value(Gmin, 8, clipa.format.bits_per_sample)
        Gmax = scale_value(Gmax, 8, clipa.format.bits_per_sample)
        Bmin = scale_value(Bmin, 8, clipa.format.bits_per_sample)
        Bmax = scale_value(Bmax, 8, clipa.format.bits_per_sample)

    if clipa.format.bits_per_sample == 8:
        rgb = core.resize.Point(clipa, format=vs.RGB24, matrix_in_s="709")
    elif clipa.format.bits_per_sample == 10:
        rgb = core.resize.Point(clipa, format=vs.RGB30, matrix_in_s="709")
    elif clipa.format.bits_per_sample == 16:
        rgb = core.resize.Point(clipa, format=vs.RGB48, matrix_in_s="709")
    else:
        raise TypeError('RGBMaskMerge: only applicable to 8, 10 and 16 bits clips.')

    R = plane(rgb, 0)
    G = plane(rgb, 1)
    B = plane(rgb, 2)
    rgbmask = core.std.Expr(
        clips=[R, G, B],
        expr=[f"x {Rmin} > x {Rmax} < y {Gmin} > y {Gmax} < z {Bmin} > z {Bmax} < and and and and and {p} 0 ?"])

    merge = core.std.MaskedMerge(clipa=clipa, clipb=clipb, mask=rgbmask)
    clip = core.std.ShufflePlanes(clips=[merge, merge, clipb], planes=[0, 1, 2], colorfamily=vs.YUV)

    return clip


def DelFrameProp(clip: vs.VideoNode,
                 primaries: bool = True,
                 matrix: bool = True,
                 transfer: bool = True) -> vs.VideoNode:
    """
    DelFrameProp, delete primaries, matrix or transfer frame properties.
      Avoids "Unrecognized transfer characteristics" or
        "unrecognized color primaries" associated with Vapoursynth Editor
    > Usage: DelFrameProp(clip, primaries, matrix, transfer)
      * primaries, matrix, transfer are boolean, True meaning that the property is deleted (default)
    """
    props = []
    if primaries:
        props.append("_Primaries")

    if matrix:
        props.append("_Matrix")

    if transfer:
        props.append("_Transfer")

    return clip.std.RemoveFrameProps(props=props)


def autogma(clip: vs.VideoNode, adj: float = 1.3, thr: float = 0.40) -> vs.VideoNode:
    """
    Just a simple function to help identify banding.
    First plane's gamma is raised by adj. If the average pixel value is greater than thr, the output will be inverted.
    :param clip: Clip to be processed. GRAY or YUV color family is required.
    :param adj: Gamma value to be adjusted by. Must be greater than or equal to 1.
    :param thr: Threshold above which the output will be inverted. Values span from 0 to 1, as generated by PlaneStats.
    :return: Clip with first plane's gamma adjusted by adj and inverted if average value above thr.
    """
    if clip.format.color_family not in [vs.GRAY, vs.YUV]:
        raise TypeError("autogma: Only GRAY and YUV color families are supported!")
    if adj < 1:
        raise ValueError("autogma: The value for adj must be greater than or equal to 1.")

    luma = core.std.ShufflePlanes(clip, 0, vs.GRAY)
    s = luma.std.PlaneStats()

    def hilo(n: int, f: vs.VideoFrame, clip: vs.VideoNode, adj: float, thr: int) -> vs.VideoNode:
        g = core.std.Levels(clip, gamma=adj)

        if f.props.PlaneStatsAverage > thr:
            return g.std.Invert().sub.Subtitle("Current average: {}".format(str(f.props.PlaneStatsAverage)))
        else:
            return g.sub.Subtitle("Current average: {}".format(str(f.props.PlaneStatsAverage)))

    prc = core.std.FrameEval(luma, partial(hilo, clip=luma, adj=adj, thr=thr), prop_src=s)

    if clip.format.color_family == vs.YUV:
        return core.std.ShufflePlanes([prc, clip], [0, 1, 2], vs.YUV)
    else:
        return prc


def FixColumnBrightnessProtect2(clip: vs.VideoNode, column: int, adj_val: int = 0, prot_val: int = 20) -> vs.VideoNode:
    return FixBrightnessProtect2(clip, column=column, adj_column=adj_val, prot_val=prot_val)


def FixRowBrightnessProtect2(clip: vs.VideoNode, row: int, adj_val: int = 0, prot_val: int = 20) -> vs.VideoNode:
    return FixBrightnessProtect2(clip, row=row, adj_row=adj_val, prot_val=prot_val)


def FixBrightnessProtect2(clip: vs.VideoNode,
                          row: Optional[Union[int, List[int]]] = None,
                          adj_row: Optional[Union[int, List[int]]] = None,
                          column: Optional[Union[int, List[int]]] = None,
                          adj_column: Optional[Union[int, List[int]]] = None,
                          prot_val: int = 20) -> vs.VideoNode:
    return rektlvls(clip, rownum=row, rowval=adj_row, colnum=column, colval=adj_column, prot_val=prot_val)


def FixColumnBrightness(clip: vs.VideoNode,
                        column: int,
                        input_low: int = 16,
                        input_high: int = 235,
                        output_low: int = 16,
                        output_high: int = 235) -> vs.VideoNode:
    hbd = Depth(clip, 32)
    lma = hbd.std.ShufflePlanes(0, vs.GRAY)

    def adj(x):
        return core.std.Levels(x,
                               min_in=scale_value(input_low, 8, 32, scale_offsets=True),
                               max_in=scale_value(input_high, 8, 32, scale_offsets=True),
                               min_out=scale_value(output_low, 8, 32, scale_offsets=True),
                               max_out=scale_value(output_high, 8, 32, scale_offsets=True),
                               planes=0)

    prc = rekt_fast(lma, adj, left=column, right=clip.width - column - 1)

    if clip.format.color_family == vs.YUV:
        prc = core.std.ShufflePlanes([prc, hbd], [0, 1, 2], vs.YUV)

    return Depth(prc, clip.format.bits_per_sample)


def FixRowBrightness(clip: vs.VideoNode,
                     row: int,
                     input_low: int = 16,
                     input_high: int = 235,
                     output_low: int = 16,
                     output_high: int = 235) -> vs.VideoNode:
    hbd = Depth(clip, 32)
    lma = hbd.std.ShufflePlanes(0, vs.GRAY)

    def adj(x):
        return core.std.Levels(x,
                               min_in=scale_value(input_low, 8, 32, scale_offsets=True),
                               max_in=scale_value(input_high, 8, 32, scale_offsets=True),
                               min_out=scale_value(output_low, 8, 32, scale_offsets=True),
                               max_out=scale_value(output_high, 8, 32, scale_offsets=True),
                               planes=0)

    prc = rekt_fast(lma, adj, top=row, bottom=clip.height - row - 1)

    if clip.format.color_family == vs.YUV:
        prc = core.std.ShufflePlanes([prc, hbd], [0, 1, 2], vs.YUV)

    return Depth(prc, clip.format.bits_per_sample)


#####################
#      Exports      #
#####################

__all__ = [
    "DelFrameProp",
    "FixBrightnessProtect2",
    "FixColumnBrightness",
    "FixColumnBrightnessProtect2",
    "FixRowBrightness",
    "FixRowBrightnessProtect2",
    "LumaMaskMerge",
    "RGBMaskMerge",
    "autogma",
]

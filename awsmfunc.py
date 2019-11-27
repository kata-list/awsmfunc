import vapoursynth as vs
from vapoursynth import core
from functools import partial
import math
from vsutil import plane, get_subsampling
import fvsfunc as fvf
from rekt import rektlvl, rektlvls

"""
To-do list:

 - CropResize: default chroma fill might make more sense
 - Figure out if BlackBorders even makes sense
 - CropResizeReader needs cfill
"""


def FixColumnBrightnessProtect2(clip, column, adj_val=0, prot_val=20):
    return rektlvl(clip, column, adj_val, "column", prot_val)


def FixRowBrightnessProtect2(clip, row, adj_val=0, prot_val=20):
    return rektlvl(clip, row, adj_val, "row", prot_val)


FixBrightnessProtect2 = rektlvls


def FixColumnBrightness(clip, column, min_in=16, max_in=235, min_out=16, max_out=235):
    hbd = fvf.Depth(clip, 16)
    lma = hbd.std.ShufflePlanes(0, vs.GRAY)
    adj = lambda x: core.std.Levels(x, min_in=min_in << 8, max_in=max_in << 8, min_out=min_out << 8,
                                    max_out=max_out << 8, planes=0)
    prc = rekt_fast(lma, adj, left=column, right=clip.width - column - 1)
    if clip.format.color_family is vs.YUV:
        prc = core.std.ShufflePlanes([prc, hbd], [0, 1, 2], vs.YUV)
    return fvf.Depth(prc, clip.format.bits_per_sample)


def FixRowBrightness(clip, row, min_in=16, max_in=235, min_out=16, max_out=235):
    hbd = fvf.Depth(clip, 16)
    lma = hbd.std.ShufflePlanes(0, vs.GRAY)
    adj = lambda x: core.std.Levels(x, min_in=min_in << 8, max_in=max_in << 8, min_out=min_out << 8,
                                    max_out=max_out << 8, planes=0)
    prc = rekt_fast(lma, adj, top=row, bottom=clip.height - row - 1)
    if clip.format.color_family is vs.YUV:
        prc = core.std.ShufflePlanes([prc, hbd], [0, 1, 2], vs.YUV)
    return fvf.Depth(prc, clip.format.bits_per_sample)


GetPlane = plane

ReplaceFrames = fvf.ReplaceFramesSimple


def bbmod(clip, top=0, bottom=0, left=0, right=0, blur=20, cTop=None, cBottom=None, cLeft=None, cRight=None):
    """
    quietvoid's bbmod helper for a significant speedup from cropping unnecessary pixels before processing.
    Thresh value is also automatically determined based on the clip's bit depth.
    :param clip: Clip to be processed.
    :param top: Top rows to be processed.
    :param bottom: Bottom rows to be processed.
    :param left: Left columns to be processed.
    :param right: Right columns to be processed.
    :param blur: Processing strength, lower values are more aggressive.
    :param cTop: Legacy top.
    :param cBottom: Legacy bottom.
    :param cLeft: Legacy left.
    :param cRight: Legacy right.
    :return: Clip with color offsets fixed.
    """

    if cTop is not None:
        top = cTop

    if cBottom is not None:
        bottom = cBottom

    if cLeft is not None:
        left = cLeft

    if cRight is not None:
        right = cRight

    depth = clip.format.bits_per_sample
    thresh = int(math.pow(2, depth - 1))

    filtered = clip

    c_left = max(left * 2, 4)
    c_right = max(right * 2, 4)
    c_top = max(top * 2, 4)
    c_bottom = max(bottom * 2, 4)

    f_width, f_height = filtered.width, filtered.height

    if left > 0 and right > 0:
        l = filtered.std.Crop(left=0, right=f_width - c_left, top=0, bottom=0)
        m = filtered.std.Crop(left=c_left, right=c_right, top=0, bottom=0)
        r = filtered.std.Crop(left=f_width - c_right, right=0, top=0, bottom=0)

        l = bbmoda(l, cTop=0, cBottom=0, cLeft=left, cRight=0, thresh=thresh, blur=blur)
        r = bbmoda(r, cTop=0, cBottom=0, cLeft=0, cRight=right, thresh=thresh, blur=blur)

        filtered = core.std.StackHorizontal(clips=[l, m, r])

    if left > 0 and right == 0:
        l = filtered.std.Crop(left=0, right=f_width - c_left, top=0, bottom=0)
        m = filtered.std.Crop(left=c_left, right=0, top=0, bottom=0)

        l = bbmoda(l, cTop=0, cBottom=0, cLeft=left, cRight=0, thresh=thresh, blur=blur)

        filtered = core.std.StackHorizontal(clips=[l, m])

    if left == 0 and right > 0:
        r = filtered.std.Crop(left=f_width - c_right, right=0, top=0, bottom=0)
        m = filtered.std.Crop(left=0, right=c_right, top=0, bottom=0)

        r = bbmoda(r, cTop=0, cBottom=0, cLeft=0, cRight=right, thresh=thresh, blur=blur)

        filtered = core.std.StackHorizontal(clips=[m, r])

    if top > 0 and bottom > 0:
        t = filtered.std.Crop(left=0, right=0, top=0, bottom=f_height - c_top)
        m = filtered.std.Crop(left=0, right=0, top=c_top, bottom=c_bottom)
        b = filtered.std.Crop(left=0, right=0, top=f_height - c_bottom, bottom=0)

        t = bbmoda(t, cTop=top, cBottom=0, cLeft=0, cRight=0, thresh=thresh, blur=blur)
        b = bbmoda(b, cTop=0, cBottom=bottom, cLeft=0, cRight=0, thresh=thresh, blur=blur)

        filtered = core.std.StackVertical(clips=[t, m, b])

    if top > 0 and bottom == 0:
        t = filtered.std.Crop(left=0, right=0, top=0, bottom=f_height - c_top)
        m = filtered.std.Crop(left=0, right=0, top=c_top, bottom=0)

        t = bbmoda(t, cTop=top, cBottom=0, cLeft=0, cRight=0, thresh=thresh, blur=blur)

        filtered = core.std.StackVertical(clips=[t, m])

    if top == 0 and bottom > 0:
        b = filtered.std.Crop(left=0, right=0, top=f_height - c_bottom, bottom=0)
        m = filtered.std.Crop(left=0, right=0, top=0, bottom=c_bottom)

        b = bbmoda(b, cTop=0, cBottom=bottom, cLeft=0, cRight=0, thresh=thresh, blur=blur)

        filtered = core.std.StackVertical(clips=[m, b])

    return filtered


def bbmoda(c, cTop=0, cBottom=0, cLeft=0, cRight=0, thresh=128, blur=999):
    """
    From sgvsfunc.
    bbmod, port from Avisynth's function, a mod of BalanceBorders
      The function changes the extreme pixels of the clip, to fix or attenuate dirty borders
      Any bit depth
      Inspired from BalanceBorders from https://github.com/WolframRhodium/muvsfunc/ and https://github.com/fdar0536/Vapoursynth-BalanceBorders/
    > Usage: bbmoda(c, cTop, cBottom, cLeft, cRight, thresh, blur)
      * c: Input clip. The image area "in the middle" does not change during processing.
           The clip can be any format, which differs from Avisynth's equivalent.
      * cTop, cBottom, cLeft, cRight (int, 0-inf): The number of variable pixels on each side.
      * thresh (int, 0~128, default 128): Threshold of acceptable changes for local color matching in 8 bit scale.
        Recommended: 0~16 or 128
      * blur (int, 1~inf, default 999): Degree of blur for local color matching.
        Smaller values give a more accurate color match, larger values give a more accurate picture transfer.
        Recommended: 1~20 or 999
      Notes:
        1) At default values ​​of thresh = 128 blur = 999:
           You will get a series of pixels that have been changed only by selecting the color for each row in its entirety, without local selection;
           The colors of neighboring pixels may be very different in some places, but there will be no change in the nature of the picture.
           With thresh = 128 and blur = 1 you get almost the same rows of pixels, i.e. The colors between them will coincide completely, but the original pattern will be lost.
        2) Beware of using a large number of pixels to change in combination with a high level of "thresh",
           and a small "blur" that can lead to unwanted artifacts "in a clean place".
           For each function call, try to set as few pixels as possible to change and as low a threshold as possible "thresh" (when using blur 0..16).
    """
    funcName = "bbmod"

    if not isinstance(c, vs.VideoNode):
        raise TypeError(funcName + ': \"c\" must be a clip!')

    if c.format.sample_type != vs.INTEGER:
        raise TypeError(funcName + ': \"c\" must be integer format!')

    if blur <= 0:
        raise ValueError(funcName + ': \'blur\' have not a correct value! (0 ~ inf]')

    if thresh <= 0:
        raise ValueError(funcName + ': \'thresh\' have not a correct value! (0 ~ inf]')

    def btb(c, cTop, thresh, blur):

        cWidth = c.width
        cHeight = c.height
        cTop = min(cTop, cHeight - 1)
        blurWidth = max(8, math.floor(cWidth / blur))

        c2 = core.resize.Point(c, cWidth * 2, cHeight * 2)
        last = core.std.CropAbs(c2, cWidth * 2, 2, 0, cTop * 2)
        last = core.resize.Point(last, cWidth * 2, cTop * 2)
        scale128 = str(scale(128, c.format.bits_per_sample))
        exprchroma = "2 * abs(x - " + scale128 + ")"
        referenceBlurChroma = mt_lut(clip=last, expr=exprchroma).resize.Bicubic(blurWidth * 2, cTop * 2,
                                                                                filter_param_a=1,
                                                                                filter_param_b=0).resize.Bicubic(
            cWidth * 2, cTop * 2, filter_param_a=1, filter_param_b=0)
        referenceBlur = core.resize.Bicubic(last, blurWidth * 2, cTop * 2, filter_param_a=1,
                                            filter_param_b=0).resize.Bicubic(cWidth * 2, cTop * 2, filter_param_a=1,
                                                                             filter_param_b=0)

        original = core.std.CropAbs(c2, cWidth * 2, cTop * 2, 0, 0)

        last = core.resize.Bicubic(original, blurWidth * 2, cTop * 2, filter_param_a=1, filter_param_b=0)

        originalBlurChroma = mt_lut(clip=last, expr=exprchroma).resize.Bicubic(blurWidth * 2, cTop * 2,
                                                                               filter_param_a=1,
                                                                               filter_param_b=0).resize.Bicubic(
            cWidth * 2, cTop * 2, filter_param_a=1, filter_param_b=0)
        originalBlur = core.resize.Bicubic(last, blurWidth * 2, cTop * 2, filter_param_a=1,
                                           filter_param_b=0).resize.Bicubic(cWidth * 2, cTop * 2, filter_param_a=1,
                                                                            filter_param_b=0)

        expruv = "z y / 8 min 0.4 max x " + scale128 + " - * " + scale128 + " +"
        balancedChroma = core.std.Expr(clips=[original, originalBlurChroma, referenceBlurChroma],
                                       expr=["", expruv, expruv])
        scale16 = str(scale(16, c.format.bits_per_sample))
        yexpr = "z " + scale16 + " - y " + scale16 + " - / 8 min 0.4 max x " + scale16 + " - * " + scale16 + " +"
        uvexpr = "z y - x +"
        balancedLuma = core.std.Expr(clips=[balancedChroma, originalBlur, referenceBlur], expr=[yexpr, uvexpr, uvexpr])

        difference = core.std.MakeDiff(balancedLuma, original, planes=[0, 1, 2])

        Tp = scale(128 + thresh, c.format.bits_per_sample)
        Tm = scale(128 - thresh, c.format.bits_per_sample)
        expr = 'x {0} > {0} x ?'.format(Tp)
        difference = core.std.Expr(clips=difference, expr=[expr, expr, expr])
        expr = 'x {0} < {0} x ?'.format(Tm)
        difference = core.std.Expr(clips=difference, expr=[expr, expr, expr])

        last = core.std.MergeDiff(original, difference, planes=[0, 1, 2])

        last = core.std.StackVertical(
            clips=[last, core.std.CropAbs(c2, cWidth * 2, (cHeight - cTop) * 2, 0, cTop * 2)]).resize.Point(cWidth,
                                                                                                            cHeight)

        return last

    c = btb(c, cTop, thresh, blur).std.Transpose().std.FlipHorizontal() if cTop > 0 else core.std.Transpose(
        c).std.FlipHorizontal()
    c = btb(c, cLeft, thresh, blur).std.Transpose().std.FlipHorizontal() if cLeft > 0 else core.std.Transpose(
        c).std.FlipHorizontal()
    c = btb(c, cBottom, thresh, blur).std.Transpose().std.FlipHorizontal() if cBottom > 0 else core.std.Transpose(
        c).std.FlipHorizontal()
    c = btb(c, cRight, thresh, blur).std.Transpose().std.FlipHorizontal() if cRight > 0 else core.std.Transpose(
        c).std.FlipHorizontal()

    return c


def BlackBorders(clip, left=0, right=0, top=0, bottom=0):
    '''	
    BlackBorders, avoids dirty lines introduced by AddBorders. From sgvsfunc.
      Actually avoids dirty lines *most of the time*, but borders may stay slightly dirty where there are vivid colors
    > Usage: BlackBorders(clip, left, right, top, bottom)
      * left, right, top, bottom are the thicknesses of black borders in pixels 
    '''
    import adjust

    if not (left % 2 == 0 and right % 2 == 0 and top % 2 == 0 and bottom % 2 == 0):
        raise ValueError('BlackBorders: border size needs to be mod 2.')

    if left > 0:
        clip = core.std.AddBorders(clip=clip, left=left)

    if right > 0:

        copy = core.std.Crop(clip, left=clip.width - 2)
        flip = core.std.FlipHorizontal(copy)
        desat = adjust.Tweak(flip, sat=0.4)
        stack = core.std.StackHorizontal([clip, desat])
        clip1 = FixColumnBrightness(clip=stack, column=clip.width, input_low=16, input_high=255, output_low=16,
                                    output_high=16, scale_inputs=True)
        clip = FixColumnBrightness(clip=clip1, column=clip.width + 1, input_low=16, input_high=255, output_low=16,
                                   output_high=16, scale_inputs=True)
        if right > 2:
            clip = core.std.AddBorders(clip=clip, right=right - 2)

    if top > 0:

        copy = core.std.Crop(clip, bottom=clip.height - 2)
        flip = core.std.FlipVertical(copy)
        desat = adjust.Tweak(flip, sat=0.4)
        stack = core.std.StackVertical([desat, clip])
        clip1 = FixRowBrightness(clip=stack, row=0, input_low=16, input_high=255, output_low=16, output_high=16,
                                 scale_inputs=True)
        clip = FixRowBrightness(clip=clip1, row=1, input_low=16, input_high=255, output_low=16, output_high=16,
                                scale_inputs=True)
        if top > 2:
            clip = core.std.AddBorders(clip=clip, top=top - 2)

    if bottom > 0:

        copy = core.std.Crop(clip, top=clip.height - 2)
        flip = core.std.FlipVertical(copy)
        desat = adjust.Tweak(flip, sat=0.4)
        stack = core.std.StackVertical([clip, desat])
        clip1 = FixRowBrightness(clip=stack, row=clip.height, input_low=16, input_high=255, output_low=16,
                                 output_high=16, scale_inputs=True)
        clip = FixRowBrightness(clip=clip1, row=clip.height + 1, input_low=16, input_high=255, output_low=16,
                                output_high=16, scale_inputs=True)
        if bottom > 2:
            clip = core.std.AddBorders(clip=clip, bottom=bottom - 2)

    return clip


def CropResize(clip, width=None, height=None, left=0, right=0, top=0, bottom=0, bb=None, fill=[0, 0, 0, 0], cfill=None,
               resizer='spline36', filter_param_a=None, filter_param_b=None) -> vs.VideoNode:
    '''
    Originally from sgvsfunc.  Added chroma filling option.
    This function is a wrapper around cropping and resizing with the option to fill and remove columns/rows.
    :param clip: Clip to be processed.
    :param width: Width of output clip.  If height is specified without width, width is auto-calculated.
    :param height: Height of output clip.  If width is specified without height, height is auto-calculated.
    :param left: Left offset of resized clip.
    :param right: Right offset of resized clip.
    :param top: Top offset of resized clip.
    :param bottom: Bottom offset of resized clip.
    :param bb: Parameters to be parsed to bbmod: cTop, cBottom, cLeft, cRight[, thresh=128, blur=999].
    :param fill: Parameters to be parsed to fb.FillBorders: left, right, top, bottom.
    :param cfill: If a list is specified, same as fill for chroma planes exclusively.  Else, a lambda function can be
                  specified, e.g. cfill=lambda c: c.edgefixer.ContinuityFixer(left=0, top=0, right=[2, 4, 4], bottom=0).
    :param resizer: Resize kernel to be used.  For internal resizers, use strings, else lambda functions can be used.
    :param filter_param_a, filter_param_b: Filter parameters for internal resizers, b & c for bicubic, taps for lanczos.
    :return: Resized clip.
    '''
    if len(fill) == 4:
        if left - int(fill[0]) >= 0 and right - int(fill[1]) >= 0 and top - int(fill[2]) >= 0 and bottom - int(
                fill[3]) >= 0:
            left = left - int(fill[0])
            right = right - int(fill[1])
            top = top - int(fill[2])
            bottom = bottom - int(fill[3])
        else:
            raise ValueError('CropResize: filling exceeds cropping.')
    else:
        raise TypeError('CropResize: fill arguments not valid.')

    lr = left % 2
    rr = right % 2
    tr = top % 2
    br = bottom % 2

    if (width is None) and (height is None):
        width = clip.width
        height = clip.height
        rh = rw = 1
    elif width is None:
        rh = rw = height / (clip.height - top - bottom)
    elif height is None:
        rh = rw = width / (clip.width - left - right)
    else:
        rh = height / clip.height
        rw = width / clip.width

    w = round(((clip.width - left - right) * rw) / 2) * 2
    h = round(((clip.height - top - bottom) * rh) / 2) * 2

    if bb != None:
        if len(bb) == 4:
            bb.append(128)
            bb.append(999)
        elif len(bb) != 6:
            raise TypeError('CropResize: bbmod arguments not valid.')

    cropeven = core.std.Crop(clip, left=left - lr, right=right - rr, top=top - tr, bottom=bottom - br)

    cropeven = core.fb.FillBorders(cropeven, left=lr + int(fill[0]), right=rr + int(fill[1]), top=tr + int(fill[2]),
                                   bottom=br + int(fill[3]), mode="fillmargins")

    if cfill is not None:
        if isinstance(cfill, list):
            cfb = core.fb.FillBorders(cropeven, cfill[0], cfill[1], cfill[2], cfill[3])
            cropeven = core.std.Merge(cfb, cropeven, [1, 0])
        else:
            cropeven = cfill(cropeven)

    if bb != None:
        bb = [int(bb[0]) + lr + int(fill[0]), int(bb[1]) + rr + int(fill[1]), int(bb[2]) + tr + int(fill[2]),
              int(bb[3]) + br + int(fill[3]), int(bb[4]), int(bb[5])]
        cropeven = bbmod(c=cropeven, cTop=int(bb[2]) + tr, cBottom=int(bb[3]) + br, cLeft=int(bb[0]) + lr,
                         cRight=int(bb[1]) + rr, thresh=int(bb[4]), blur=int(bb[5]))

    if resizer.lower() == 'bilinear':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='bilinear')
        else:
            resized = core.resize.Bilinear(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                           src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br)
    elif resizer.lower() == 'bicubic':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='bicubic', a1=filter_param_a,
                                         a2=filter_param_b)
        else:
            resized = core.resize.Bicubic(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                          src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br,
                                          filter_param_a=filter_param_a, filter_param_b=filter_param_b)
    elif resizer.lower() == 'point':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='point')
        else:
            resized = core.resize.Point(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                        src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br)
    elif resizer.lower() == 'lanczos':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='lanczos', taps=filter_param_a)
        else:
            resized = core.resize.Lanczos(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                          src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br,
                                          filter_param_a=filter_param_a)
    elif resizer.lower() == 'spline16':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='spline16')
        else:
            resized = core.resize.Spline16(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                           src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br)
    elif resizer.lower() == 'spline36':
        if lr or tr or rr or br != 0 and cropeven.format.bits_per_sample == 16:
            resized = core.fmtc.resample(cropeven, w, h, sx=lr, sy=tr, sw=cropeven.width - lr - rr,
                                         sh=cropeven.height - tr - br, kernel='spline36')
        else:
            resized = core.resize.Spline36(clip=cropeven, width=w, height=h, src_left=lr, src_top=tr,
                                           src_width=cropeven.width - lr - rr, src_height=cropeven.height - tr - br)
    elif isinstance(resizer, str):
        raise TypeError('CropResize: Resizer "{}" unknown'.format(resizer))
    else:
        resized = resizer(cropeven)

    return resized


cr = CropResize
CR = CropResize
cropresize = CropResize


def CropResizeReader(clip, csvfile, width=None, height=None, row=None, adj_row=None, column=None, adj_column=None,
                     fill_max=2, bb=None, FixUncrop=[False, False, False, False], resizer='spline36'):
    '''
    CropResizeReader, cropResize for variable borders by loading crop values from a csv file
      Also fill small borders and fix brightness/apply bbmod relatively to the variable border
      From sgvsfunc.
    > Usage: CropResizeReader(clip, csvfile, width, height, row, adj_row, column, adj_column, fill_max, bb, FixUncrop, resizer)
      * csvfile is the path to a csv file containing in each row: <startframe> <endframe> <left> <right> <top> <bottom>
        where left, right, top, bottom are the number of pixels to crop
        Optionally, the number of pixels to fill can be appended to each line <left> <right> <top> <bottom> in order to reduce the black borders.
        Filling can be useful in case of small borders to equilibriate the number of pixels between right/top and left/bottom after resizing.
      * width and height are the dimensions of the resized clip
        If none of them is indicated, no resizing is performed. If only one of them is indicated, the other is deduced.
      * row, adj_row, column, adj_column are lists of values to use FixBrightnessProtect2, where row/column is relative to the border defined by the cropping
      * Borders <=fill_max will be filled instead of creating a black border
      * bb is a list containing bbmod values [cLeft, cRight, cTop, cBottom, thresh, blur] where thresh and blur are optional.
        Mind the order: it is different from usual cTop, cBottom, cLeft, cRight
      * FixUncrop is a list of 4 booleans [left right top bottom]
        False means that FixBrightness/bbmod is only apply where crop>0, True means it is applied on the whole clip
      * resizer should be Bilinear, Bicubic, Point, Lanczos, Spline16 or Spline36 (default)
    '''
    import csv

    if len(FixUncrop) != 4:
        raise TypeError('CropResizeReader: FixUncrop argument not valid.')

    if (width is None) and (height is None):
        width = clip.width
        height = clip.height
        rh = rw = 1
    elif width is None:
        rh = rw = height / clip.height
        width = round((clip.width * rh) / 2) * 2
    elif height is None:
        rh = rw = width / clip.width
        height = round((clip.height * rw) / 2) * 2
    else:
        rh = height / clip.height
        rw = width / clip.width

    filtered = clip

    if bb != None:
        if len(bb) == 4:
            bb.append(128)
            bb.append(999)
        elif len(bb) != 6:
            raise TypeError('CropResizeReader: bbmod arguments not valid.')
        bbtemp = [bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]]
        if FixUncrop[0] == False:
            bbtemp[0] = 0
        if FixUncrop[1] == False:
            bbtemp[1] = 0
        if FixUncrop[2] == False:
            bbtemp[2] = 0
        if FixUncrop[3] == False:
            bbtemp[3] = 0
        filtered = bbmod(c=filtered, cTop=bbtemp[2], cBottom=bbtemp[3], cLeft=bbtemp[0], cRight=bbtemp[1],
                         thresh=bbtemp[4], blur=bbtemp[5])

    resized = core.resize.Spline36(clip=filtered, width=width, height=height)

    with open(csvfile) as cropcsv:
        cropzones = csv.reader(cropcsv, delimiter=' ')
        for zone in cropzones:

            cl = int(zone[2])
            cr = int(zone[3])
            ct = int(zone[4])
            cb = int(zone[5])

            filteredtemp = clip

            if row is not None:
                if not isinstance(row, list):
                    row = [int(row)]
                    adj_row = [int(adj_row)]
                for i in range(len(row)):
                    if row[i] < 0:
                        if FixUncrop[3] == True or cb > 0:
                            filteredtemp = FixBrightnessProtect2(clip=filteredtemp, row=int(row[i]) - cb,
                                                                 adj_row=adj_row[i])
                    else:
                        if FixUncrop[2] == True or ct > 0:
                            filteredtemp = FixBrightnessProtect2(clip=filteredtemp, row=ct + int(row[i]),
                                                                 adj_row=adj_row[i])

            if column is not None:
                if not isinstance(column, list):
                    column = [int(column)]
                    adj_column = [int(adj_column)]
                for j in range(len(column)):
                    if column[j] < 0:
                        if FixUncrop[1] == True or cr > 0:
                            filteredtemp = FixBrightnessProtect2(clip=filteredtemp, column=int(column[j]) - cr,
                                                                 adj_column=adj_column[j])
                    else:
                        if FixUncrop[0] == True or cl > 0:
                            filteredtemp = FixBrightnessProtect2(clip=filteredtemp, column=cl + int(column[j]),
                                                                 adj_column=adj_column[j])

            bbtemp = None
            if bb != None:
                bbtemp = [bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]]
                if FixUncrop[0] == False and cl == 0:
                    bbtemp[0] = 0
                if FixUncrop[1] == False and cr == 0:
                    bbtemp[1] = 0
                if FixUncrop[2] == False and ct == 0:
                    bbtemp[2] = 0
                if FixUncrop[3] == False and cb == 0:
                    bbtemp[3] = 0

            if cl > 0 and cl <= fill_max:
                filteredtemp = core.fb.FillBorders(filteredtemp, left=cl, mode="fillmargins")
                if bbtemp != None:
                    bbtemp[0] = int(bbtemp[0]) + cl
                cl = 0

            if cr > 0 and cr <= fill_max:
                filteredtemp = core.fb.FillBorders(filteredtemp, right=cr, mode="fillmargins")
                if bbtemp != None:
                    bbtemp[1] = int(bbtemp[1]) + cr
                cr = 0

            if ct > 0 and ct <= fill_max:
                filteredtemp = core.fb.FillBorders(filteredtemp, top=ct, mode="fillmargins")
                if bbtemp != None:
                    bbtemp[2] = int(bbtemp[2]) + ct
                ct = 0

            if cb > 0 and cb <= fill_max:
                filteredtemp = core.fb.FillBorders(filteredtemp, bottom=cb, mode="fillmargins")
                if bbtemp != None:
                    bbtemp[3] = int(bbtemp[3]) + cb
                cb = 0

            if len(zone) == 6:
                fill = [0, 0, 0, 0]
            elif len(zone) == 10:
                fill = [int(zone[6]), int(zone[7]), int(zone[8]), int(zone[9])]
            else:
                raise TypeError('CropResizeReader: csv file not valid.')

            resizedcore = CropResize(filteredtemp, width=width, height=height, left=cl, right=cr, top=ct, bottom=cb,
                                     bb=bbtemp, fill=fill, resizer=resizer)

            x = round((cl * rw) / 2) * 2
            y = round((ct * rh) / 2) * 2
            resizedfull = BlackBorders(resizedcore, left=x, right=width - resizedcore.width - x, top=y,
                                       bottom=height - resizedcore.height - y)

            maps = "[" + zone[0] + " " + zone[1] + "]"
            resized = ReplaceFrames(resized, resizedfull, mappings=maps)
            filtered = ReplaceFrames(filtered, filteredtemp, mappings=maps)

    return resized


def DebandReader(clip, csvfile, grain=64, range=30):
    '''
    DebandReader, read a csv file to apply a f3kdb filter for given strengths and frames. From sgvsfunc.
    > Usage: DebandReader(clip, csvfile, grain, range)
      * csvfile is the path to a csv file containing in each row: <startframe> <endframe> <strength>
      * grain is passed as grainy and grainc in the f3kdb filter
      * range is passed as range in the f3kdb filter
    '''
    import csv

    filtered = clip

    with open(csvfile) as debandcsv:
        csvzones = csv.reader(debandcsv, delimiter=' ')
        for row in csvzones:
            strength = row[2]

            db = core.f3kdb.Deband(clip, y=strength, cb=strength, cr=strength, grainy=grain, grainc=grain,
                                   dynamic_grain=True, range=range)

            filtered = ReplaceFrames(filtered, db, mappings="[" + row[0] + " " + row[1] + "]")

    return filtered


def LumaMaskMerge(clipa, clipb, threshold=128, invert=False, scale_inputs=False, planes=0):
    '''
    LumaMaskMerge, merges clips using a binary mask defined by a brightness level. From sgvsfunc, with added planes.
    > Usage: LumaMaskMerge(clipa, clipb, threshold, invert, scale_inputs)
      * threshold is the brightness level. clipb is applied where the brightness is below threshold
      * If invert = True, clipb is applied where the brightness is above threshold
      * scale_inputs = True scales threshold from 8bits to current bit depth.
      * Use planes to specify which planes should be merged from clipb into clipa. Default is first plane.
    '''
    p = (1 << clipa.format.bits_per_sample) - 1

    if scale_inputs == True:
        threshold = scale(threshold, clipa.format.bits_per_sample)

    if invert == False:
        mask = core.std.Binarize(clip=clipa.std.ShufflePlanes(0, vs.GRAY), threshold=threshold, v0=p, v1=0)
    elif invert == True:
        mask = core.std.Binarize(clip=clipa.std.ShufflePlanes(0, vs.GRAY), threshold=threshold, v0=0, v1=p)

    merge = core.std.MaskedMerge(clipa=clipa, clipb=clipb, mask=mask, planes=planes)

    return merge


def RGBMaskMerge(clipa, clipb, Rmin, Rmax, Gmin, Gmax, Bmin, Bmax, scale_inputs=False):
    '''
    RGBMaskMerge, merges clips using a binary mask defined by a RGB range. From sgvsfunc.
    > Usage: RGBMaskMerge(clipa, clipb, Rmin, Rmax, Gmin, Gmax, Bmin, Bmax, scale_inputs)
      * clipb is applied where Rmin < R < Rmax and Gmin < G < Gmax and Bmin < B < Bmax
      * scale_inputs = True scales Rmin, Rmax, Gmin, Gmax, Bmin, Bmax from 8bits to current bit depth (8, 10 or 16).
    '''
    p = (1 << clipa.format.bits_per_sample) - 1

    if scale_inputs == True:
        Rmin = scale(Rmin, clipa.format.bits_per_sample)
        Rmax = scale(Rmax, clipa.format.bits_per_sample)
        Gmin = scale(Gmin, clipa.format.bits_per_sample)
        Gmax = scale(Gmax, clipa.format.bits_per_sample)
        Bmin = scale(Bmin, clipa.format.bits_per_sample)
        Bmax = scale(Bmax, clipa.format.bits_per_sample)

    if clipa.format.bits_per_sample == 8:
        rgb = core.resize.Point(clipa, format=vs.RGB24, matrix_in_s="709")
    elif clipa.format.bits_per_sample == 10:
        rgb = core.resize.Point(clipa, format=vs.RGB30, matrix_in_s="709")
    elif clipa.format.bits_per_sample == 16:
        rgb = core.resize.Point(clipa, format=vs.RGB48, matrix_in_s="709")
    else:
        raise TypeError('RGBMaskMerge: only applicable to 8, 10 and 16 bits clips.')

    R = GetPlane(rgb, 0)
    G = GetPlane(rgb, 1)
    B = GetPlane(rgb, 2)
    rgbmask = core.std.Expr(clips=[R, G, B], expr=[
        "x " + str(Rmin) + " > x " + str(Rmax) + " < y " + str(Gmin) + " > y " + str(Gmax) + " < z " + str(
            Bmin) + " > z " + str(Bmax) + " < and and and and and " + str(p) + " 0 ?"])
    out = core.std.ShufflePlanes(clips=[rgbmask], planes=[0], colorfamily=vs.RGB)

    merge = core.std.MaskedMerge(clipa=clipa, clipb=clipb, mask=rgbmask)
    clip = core.std.ShufflePlanes(clips=[merge, merge, clipb], planes=[0, 1, 2], colorfamily=vs.YUV)

    return clip


def ScreenGen(clip, folder, video_type, frame_numbers="screens.txt"):
    """
    quietvoid's screenshot generator.
    Generates screenshots from a list of frame numbers
    folder is the folder name that is created
    video_type is the final name appended
    frame_numbers is the file path to the list, defaults to screens.txt

    > Usage: ScreenGen(src, "Screenshots", "a")
             ScreenGen(enc, "Screenshots", "b")
    """
    import os

    frame_num_path = "./{name}".format(name=frame_numbers)
    folder_path = "./{name}".format(name=folder)

    if os.path.isfile(frame_num_path):
        with open(frame_numbers) as f:
            screens = f.readlines()

        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)

        screens = [int(x.strip()) for x in screens]

        for i, num in enumerate(screens, start=1):
            filename = "{path}/{:02d}{type}.png".format(i, path=folder_path, type=video_type)
            core.imwri.Write(clip.resize.Spline36(format=vs.RGB24, matrix_in_s="709"), "PNG", filename,
                             overwrite=True).get_frame(num)


def DynamicTonemap(clip, show=False):
    """
    quietvoid's dynamic tonemapping function.
    :param clip: HDR clip.
    :param show: Whether to show nits values.
    :return: SDR clip.
    """

    def __dt(n, f, clip, show):
        import numpy as np

        ST2084_PEAK_LUMINANCE = 10000
        ST2084_M1 = 0.1593017578125
        ST2084_M2 = 78.84375
        ST2084_C1 = 0.8359375
        ST2084_C2 = 18.8515625
        ST2084_C3 = 18.6875

        def st2084_eotf(x):
            y = float(0.0)
            if (x > 0.0):
                xpow = math.pow(x, float(1.0) / ST2084_M2)
                num = max(xpow - ST2084_C1, float(0.0))
                den = max(ST2084_C2 - ST2084_C3 * xpow, float('-inf'))
                y = float(math.pow(num / den, float(1.0) / ST2084_M1))

            return y

        luma_arr = f.get_read_array(0)
        luma_max = np.percentile(luma_arr, float(99.99))
        nits_max = st2084_eotf(luma_max / 65535) * ST2084_PEAK_LUMINANCE

        # Don't go below 120 nits
        nits = max(math.ceil(nits_max), 100)

        # Tonemap
        clip = clip.resize.Spline36(transfer_in_s="st2084", transfer_s="709", matrix_in_s="ictcp", matrix_s="709",
                                    primaries_in_s="2020", primaries_s="709", range_in_s="full", range_s="limited",
                                    dither_type="none", nominal_luminance=nits)

        if show:
            clip = core.sub.Subtitle(clip, "Peak nits: {}, Target: {} nits".format(nits_max, nits))

        return clip

    clip = clip.resize.Spline36(format=vs.YUV444P16, matrix_in_s="2020ncl", matrix_s="ictcp", range_in_s="limited",
                                range_s="full", dither_type="none")

    luma_props = core.std.PlaneStats(clip, plane=0)
    tonemapped_clip = core.std.FrameEval(clip, partial(__dt, clip=clip, show=show), prop_src=[luma_props])

    tonemapped_clip = tonemapped_clip.resize.Spline36(format=vs.YUV420P10)

    return tonemapped_clip


def FillBorders(clip, left=0, right=0, top=0, bottom=0):
    """
    FillBorders wrapper that automatically sets fillmargins mode.
    """
    return core.fb.FillBorders(clip, left = left, right = right, top = top, bottom = bottom, mode = "fillmargins")

fb = FillBorders

#####################
# Utility functions #
#####################


def SelectRangeEvery(clip, every, length, offset=[0, 0]):
    '''
    SelectRangeEvery, port from Avisynth's function. From sgvsfunc.
    Offset can be an array with the first entry being the offset from the start and the second from the end.
    > Usage: SelectRangeEvery(clip, every, length, offset)
      * select <length> frames every <every> frames, starting at frame <offset>
    '''
    if isinstance(offset, int):
        offset = [offset, 0]
    select = core.std.Trim(clip, first=offset[0], last=clip.num_frames - 1 - offset[1])
    select = core.std.SelectEvery(select, cycle=every, offsets=range(length))
    select = core.std.AssumeFPS(select, fpsnum=clip.fps.numerator, fpsden=clip.fps.denominator)

    return select


def FrameInfo(clip, title,
              style="sans-serif,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,10,10,10,1"):
    '''
    FrameInfo. From sgvsfunc, with additional style option.
    > Usage: FrameInfo(clip, title)
      * Print the frame number, the picture type and a title on each frame
    '''

    def FrameProps(n, clip):
        if "_PictType" in clip.get_frame(n).props:
            clip = core.sub.Subtitle(clip, "Frame " + str(n) + " of " + str(
                clip.num_frames) + "\nPicture type: " + clip.get_frame(n).props._PictType.decode(), style=style)
        else:
            clip = core.sub.Subtitle(clip, "Frame " + str(n) + " of " + str(clip.num_frames) + "\nPicture type: N/A",
                                     style=style)

        return clip

    clip = core.std.FrameEval(clip, partial(FrameProps, clip=clip))
    clip = core.sub.Subtitle(clip, text=['\n \n \n' + title], style=style)

    return clip


def DelFrameProp(clip, primaries=True, matrix=True, transfer=True):
    '''
    DelFrameProp, delete primaries, matrix or transfer frame properties. From sgvsfunc.
      Avoids "Unrecognized transfer characteristics" or "unrecognized color primaries" associated with Vapoursynth Editor
    > Usage: DelFrameProp(clip, primaries, matrix, transfer)
      * primaries, matrix, transfer are boolean, True meaning that the property is deleted (default)
    '''
    if primaries == True:
        clip = core.std.SetFrameProp(clip, prop="_Primaries", delete=True)

    if matrix == True:
        clip = core.std.SetFrameProp(clip, prop="_Matrix", delete=True)

    if transfer == True:
        clip = core.std.SetFrameProp(clip, prop="_Transfer", delete=True)

    return clip


def InterleaveDir(folder, PrintInfo=False, DelProp=False, first=None, repeat=False):
    '''
    InterleaveDir, load all mkv files located in a directory and interleave them. From sgvsfunc.
    > Usage: InterleaveDir(folder, PrintInfo, DelProp, first, repeat)
      * folder is the folder path
      * PrintInfo = True prints the frame number, picture type and file name on each frame
      * DelProp = True means deleting primaries, matrix and transfer characteristics
      * first is an optional clip to append in first position of the interleaving list
      * repeat = True means that the appended clip is repeated between each loaded clip from the folder
    '''
    import os

    files = sorted(os.listdir(folder))

    if first != None:
        sources = [first]
        j = 0
    else:
        sources = []
        j = -1

    for i in range(len(files)):

        if files[i].endswith('.mkv'):

            j = j + 1
            sources.append(0)
            sources[j] = core.ffms2.Source(folder + '/' + files[i])

            if first != None:
                sources[j] = core.std.AssumeFPS(clip=sources[j], src=first)

            if PrintInfo == True:
                sources[j] = FrameInfo(clip=sources[j], title=files[i])
            elif PrintInfo != False:
                raise TypeError('InterleaveDir: PrintInfo must be a boolean.')

            if DelProp == True:
                sources[j] = DelFrameProp(sources[j])
            elif DelProp != False:
                raise TypeError('InterleaveDir: DelProp must be a boolean.')

            if first != None and repeat == True:
                j = j + 1
                sources.append(0)
                sources[j] = first
            elif first != None and repeat != False:
                raise TypeError('InterleaveDir: repeat must be a boolean.')

    comparison = core.std.Interleave(sources)

    return comparison


def ExtractFramesReader(clip, csvfile):
    '''
    ExtractFramesReader, reads a csv file to extract ranges of frames. From sgvsfunc.
    > Usage: ExtractFramesReader(clip, csvfile)
      * csvfile is the path to a csv file containing in each row: <startframe> <endframe>
        the csv file may contain other columns, which will not be read
    '''
    import csv

    selec = core.std.BlankClip(clip=clip, length=1)

    with open(csvfile) as framescsv:
        csvzones = csv.reader(framescsv, delimiter=' ')
        for row in csvzones:
            start = row[0]
            end = row[1]

            selec = selec + core.std.Trim(clip, first=start, last=end)

    selec = core.std.Trim(selec, first=1)

    return selec


def fixlvls(clip, gamma=0.88, min_in=4096, max_in=60160, min_out=4096, max_out=60160, planes=0, preset=None):
    """
    A wrapper around std.Levels to fix what's commonly known as the gamma bug.
    :param clip: Processed clip.
    :param gamma: Gamma adjustment value.  Default of 0.88 is usually correct.
    :param min_in: Input minimum.
    :param max_in: Input maximum.
    :param min_out: Output minimum.
    :param max_out: Output maximum.
    :param preset: 1: standard gamma bug, 2: luma-only overflow, 3: overflow
    overflow explained: https://guide.encode.moe/encoding/video-artifacts.html#underflow--overflow
    :return: Clip with gamma adjusted or levels fixed.
    """
    clip = fvf.Depth(clip, 16)
    if preset is None:
        adj = core.std.Levels(clip, gamma=gamma, min_in=min_in, max_in=max_in, min_out=min_out, max_out=max_out,
                              planes=planes)
    elif preset == 1:
        adj = core.std.Levels(clip, gamma=gamma, min_in=4096, max_in=60160, min_out=4096, max_out=60160, planes=0)
    elif preset == 2:
        adj = core.std.Levels(clip, min_out=0, max_out=65535, min_in=4096, max_in=60160, planes=0)
    elif preset == 3:
        adj = core.std.Levels(clip, min_in=0, max_in=65535, min_out=4096, max_out=60160, planes=0)
        adj = core.std.Levels(adj, min_in=0, max_in=65535, min_out=4096, max_out=61440, planes=[1, 2])
    return fvf.Depth(adj, clip.format.bits_per_sample)


def mt_lut(clip, expr, planes=[0]):
    '''
    mt_lut, port from Avisynth's function. From sgvsfunc.
    > Usage: mt_lut(clip, expr, planes)
      * expr is an infix expression, not like avisynth's mt_lut which takes a postfix one
    '''
    minimum = 16 * ((1 << clip.format.bits_per_sample) - 1) // 256
    maximum = 235 * ((1 << clip.format.bits_per_sample) - 1) // 256

    def clampexpr(x):
        return int(max(minimum, min(round(eval(expr)), maximum)))

    return core.std.Lut(clip=clip, function=clampexpr, planes=planes)


def scale(val, bits, bits_in=8):
    """
    Scale function from havsfunc with additional val bit depth specification option.
    :param val: Value to be scaled.
    :param bits: Bit depth to be scaled to.
    :param bits_in: Input bit depth.  Default is 8-bit.
    :return: val scaled from its bit depth to bits depth.
    """
    return val * ((1 << bits) - 1) // ((1 << bits_in) - 1)


def autogma(clip, adj=1.3, thr=0.40):
    """
    From https://gitlab.com/snippets/1895974.
    Just a simple function to help identify banding.
    First plane's gamma is raised by adj. If the average pixel value is greater than thr, the output will be inverted.
    :param clip: Clip to be processed. GRAY or YUV color family is required.
    :param adj: Gamma value to be adjusted by. Must be greater than or equal to 1.
    :param thr: Threshold above which the output will be inverted. Values span from 0 to 1, as generated by PlaneStats.
    :return: Clip with first plane's gamma adjusted by adj and inverted if average value above thr.
    """
    if clip.format.color_family != (vs.YUV or vs.YUV):
        raise TypeError("autogma: Only GRAY and YUV color families are supported!")
    if adj < 1:
        raise ValueError("autogma: The value for adj must be greater than or equal to 1.")

    luma = core.std.ShufflePlanes(clip, 0, vs.GRAY)
    s = luma.std.PlaneStats()

    def hilo(n, f, clip, adj, thr):
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


def greyscale(clip):
    """
    From https://gitlab.com/snippets/1895242.
    Really stupid function. Only advisable if you're not doing any other filtering. Replaces chroma planes with gray.
    """
    if clip.format.color_family != vs.YUV:
        raise TypeError("GreyScale: YUV input is required!")
    grey = core.std.BlankClip(clip)
    return core.std.ShufflePlanes([clip, grey], [0, 1, 2], vs.YUV)


grayscale = greyscale
GreyScale = greyscale
GrayScale = greyscale
gs = greyscale

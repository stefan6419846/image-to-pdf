# This file is largely based upon the PdfImagePlugin of the `Pillow` package,
# but received further customization.
#
# Original code: https://github.com/python-pillow/Pillow/blob/2d0610888e64c9ff732bf73a59b89eb033ea3d1e/src/PIL/PdfImagePlugin.py
#
# The original `Pillow` copyright is:
#
# ---------------------------------------------------------------------------
#
# The Python Imaging Library (PIL) is
#
#     Copyright © 1997-2011 by Secret Labs AB
#     Copyright © 1995-2011 by Fredrik Lundh and contributors
#
# Pillow is the friendly PIL fork. It is
#
#     Copyright © 2010-2024 by Jeffrey A. Clark and contributors
#
# Like PIL, Pillow is licensed under the open source HPND License:
#
# By obtaining, using, and/or copying this software and/or its associated
# documentation, you agree that you have read, understood, and will comply
# with the following terms and conditions:
#
# Permission to use, copy, modify and distribute this software and its
# documentation for any purpose and without fee is hereby granted,
# provided that the above copyright notice appears in all copies, and that
# both that copyright notice and this permission notice appear in supporting
# documentation, and that the name of Secret Labs AB or the author not be
# used in advertising or publicity pertaining to distribution of the software
# without specific, written prior permission.
#
# SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
# SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
# IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
# INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
# OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.
#
# ---------------------------------------------------------------------------
#
# The original file copyright is:
#
# ---------------------------------------------------------------------------
#
# Copyright (c) 1997-2004 by Secret Labs AB.  All rights reserved.
# Copyright (c) 1996-1997 by Fredrik Lundh.
#
# See the README file for information on usage and redistribution.
#
# ---------------------------------------------------------------------------
#
# This modified implementation is subject to same HPND license with the
# following additional copyright line:
#
# ---------------------------------------------------------------------------
#
# Copyright (c) 2024 stefan6419846
#
# ---------------------------------------------------------------------------
#
# The implementation itself is based upon the unmerged changes proposed in
# https://github.com/python-pillow/Pillow/pull/8097, while incorporating
# some of the review comments, especially to use `FlateDecode` for RGBA
# images.
#
# This file aims to provide the same API as the original `PIL.PdfImagePlugin`,
# except that all the methods are public. In theory, it should be possible
# to replace the original `PdfImagePlugin` with this custom one.
#

##
# Image plugin for PDF images (output only).
##
from __future__ import annotations

import io
import math
import os
import time
import zlib
from typing import Any, IO

from PIL import Image, ImageFile, ImageSequence, PdfParser, features


__version__ = "0.1.0"

#
# --------------------------------------------------------------------

# object ids:
#  1. catalogue
#  2. pages
#  3. image
#  4. page
#  5. page contents


def save_all(im: Image.Image, fp: IO[bytes], filename: str, **kwargs: Any) -> None:
    save(im, fp, filename, save_all=True, **kwargs)


##
# (Internal) Image save plugin for the PDF format.


def _write_image(
    im: Image.Image,
    filename: str,
    existing_pdf: PdfParser.PdfParser,
    image_refs: list[PdfParser.IndirectReference],
):
    parameters = None
    decode = None
    smask = None

    # Get image characteristics

    width, height = im.size

    dict_object = {"BitsPerComponent": 8}
    if im.mode == "1":
        if features.check("libtiff"):
            filter_name = "CCITTFaxDecode"
            dict_object["BitsPerComponent"] = 1
            parameters = PdfParser.PdfArray(
                [
                    PdfParser.PdfDict(
                        {
                            "K": -1,
                            "BlackIs1": True,
                            "Columns": width,
                            "Rows": height,
                        }
                    )
                ]
            )
        else:
            filter_name = "DCTDecode"
        dict_object["ColorSpace"] = PdfParser.PdfName("DeviceGray")
        procset = "ImageB"  # grayscale
    elif im.mode in {"L", "LA"}:
        filter_name = "DCTDecode"
        dict_object["ColorSpace"] = PdfParser.PdfName("DeviceGray")
        procset = "ImageB"  # grayscale
        if im.mode == "LA":
            smask = im
            im = im.convert("L")
            im.encoderinfo = {}
    elif im.mode == "P":
        filter_name = "ASCIIHexDecode"
        palette = im.getpalette()
        dict_object["ColorSpace"] = [
            PdfParser.PdfName("Indexed"),
            PdfParser.PdfName("DeviceRGB"),
            len(palette) // 3 - 1,
            PdfParser.PdfBinary(palette),
        ]
        procset = "ImageI"  # indexed color

        if "transparency" in im.info:
            smask = im.convert("LA")
    elif im.mode == "RGB":
        filter_name = "DCTDecode"
        dict_object["ColorSpace"] = PdfParser.PdfName("DeviceRGB")
        procset = "ImageC"  # color images
    elif im.mode == "RGBA":
        filter_name = "FlateDecode"
        dict_object["ColorSpace"] = PdfParser.PdfName("DeviceRGB")
        procset = "ImageC"  # color images
        smask = im
        im = im.convert("RGB")
        im.encoderinfo = {}
    elif im.mode == "CMYK":
        filter_name = "DCTDecode"
        dict_object["ColorSpace"] = PdfParser.PdfName("DeviceCMYK")
        procset = "ImageC"  # color images
        decode = [1, 0, 1, 0, 1, 0, 1, 0]
    else:
        msg = f"cannot save mode {im.mode}"
        raise ValueError(msg)

    if smask:
        smask = smask.getchannel("A")
        smask.encoderinfo = {}

        image_ref = _write_image(smask, filename, existing_pdf, image_refs)[0]
        dict_object["SMask"] = image_ref

    #
    # image

    op = io.BytesIO()

    if filter_name == "ASCIIHexDecode":
        ImageFile._save(im, op, [("hex", (0, 0) + im.size, 0, im.mode)])
    elif filter_name == "CCITTFaxDecode":
        im.save(
            op,
            "TIFF",
            compression="group4",
            # use a single strip
            strip_size=math.ceil(width / 8) * height,
        )
    elif filter_name == "DCTDecode":
        Image.SAVE["JPEG"](im, op, filename)
    elif filter_name == "FlateDecode":
        op.write(zlib.compress(im.tobytes()))
    else:
        msg = f"unsupported PDF filter ({filter_name})"
        raise ValueError(msg)

    stream = op.getvalue()
    if filter_name == "CCITTFaxDecode":
        stream = stream[8:]
        filter_name = PdfParser.PdfArray([PdfParser.PdfName(filter_name)])

    else:
        filter_name = PdfParser.PdfName(filter_name)

    image_ref = image_refs.pop(0)
    existing_pdf.write_obj(
        image_ref,
        stream=stream,
        Type=PdfParser.PdfName("XObject"),
        Subtype=PdfParser.PdfName("Image"),
        Width=width,  # * 72.0 / x_resolution,
        Height=height,  # * 72.0 / y_resolution,
        Filter=filter_name,
        Decode=decode,
        DecodeParms=parameters,
        **dict_object,
    )

    return image_ref, procset


def save(im: Image.Image, fp: IO[bytes], filename: str, save_all: bool = False, **kwargs: Any) -> None:
    if not hasattr(im, "encoderinfo"):
        im.encoderinfo = kwargs
    is_appending = im.encoderinfo.get("append", False)
    if is_appending:
        existing_pdf = PdfParser.PdfParser(f=fp, filename=filename, mode="r+b")
    else:
        existing_pdf = PdfParser.PdfParser(f=fp, filename=filename, mode="w+b")

    dpi = im.encoderinfo.get("dpi")
    if dpi:
        x_resolution = dpi[0]
        y_resolution = dpi[1]
    else:
        x_resolution = y_resolution = im.encoderinfo.get("resolution", 72.0)

    info = {
        "title": (None if is_appending else os.path.splitext(os.path.basename(filename))[0]),
        "author": None,
        "subject": None,
        "keywords": None,
        "creator": None,
        "producer": None,
        "creationDate": None if is_appending else time.gmtime(),
        "modDate": None if is_appending else time.gmtime(),
    }
    for k, default in info.items():
        v = im.encoderinfo.get(k) if k in im.encoderinfo else default
        if v:
            existing_pdf.info[k[0].upper() + k[1:]] = v

    #
    # make sure image data is available
    im.load()

    existing_pdf.start_writing()
    existing_pdf.write_header()
    # existing_pdf.write_comment(f"created by Pillow {PILVersion} PDF driver")

    #
    # pages
    ims = [im]
    if save_all:
        append_images = im.encoderinfo.get("append_images", [])
        for append_im in append_images:
            append_im.encoderinfo = im.encoderinfo.copy()
            ims.append(append_im)
    number_of_pages = 0
    image_refs = []
    page_refs = []
    contents_refs = []
    for im in ims:
        im_number_of_pages = 1
        if save_all:
            try:
                im_number_of_pages = im.n_frames
            except AttributeError:
                # Image format does not have n_frames.
                # It is a single frame image
                pass
        number_of_pages += im_number_of_pages
        for _ in range(im_number_of_pages):
            image_refs.append(existing_pdf.next_object_id(0))
            if im.mode in {"LA", "RGBA"} or (im.mode == "P" and "transparency" in im.info):
                image_refs.append(existing_pdf.next_object_id(0))

            page_refs.append(existing_pdf.next_object_id(0))
            contents_refs.append(existing_pdf.next_object_id(0))
            existing_pdf.pages.append(page_refs[-1])

    #
    # catalog and list of pages
    existing_pdf.write_catalog()

    page_number = 0
    for im_sequence in ims:
        im_pages = ImageSequence.Iterator(im_sequence) if save_all else [im_sequence]
        for im in im_pages:
            image_ref, procset = _write_image(im, filename, existing_pdf, image_refs)

            #
            # page

            existing_pdf.write_page(
                page_refs[page_number],
                Resources=PdfParser.PdfDict(
                    ProcSet=[PdfParser.PdfName("PDF"), PdfParser.PdfName(procset)],
                    XObject=PdfParser.PdfDict(image=image_ref),
                ),
                MediaBox=[
                    0,
                    0,
                    im.width * 72.0 / x_resolution,
                    im.height * 72.0 / y_resolution,
                ],
                Contents=contents_refs[page_number],
            )

            #
            # page contents

            page_contents = b"q %f 0 0 %f 0 0 cm /image Do Q\n" % (
                im.width * 72.0 / x_resolution,
                im.height * 72.0 / y_resolution,
            )

            existing_pdf.write_obj(contents_refs[page_number], stream=page_contents)

            page_number += 1

    #
    # trailer
    existing_pdf.write_xref_and_trailer()
    if hasattr(fp, "flush"):
        fp.flush()
    existing_pdf.close()

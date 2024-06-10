# The following code is largely based upon the original tests and has mostly
# been migrated from `pytest` to plain `unittest`, although the mode-based
# tests are completely new.
#
# Original code: https://github.com/python-pillow/Pillow/blob/2d0610888e64c9ff732bf73a59b89eb033ea3d1e/Tests/test_file_pdf.py
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
# This modified implementation is subject to same HPND license with the
# following additional copyright line:
#
# ---------------------------------------------------------------------------
#
# Copyright (c) 2024 stefan6419846
#
# ---------------------------------------------------------------------------
#
from __future__ import annotations

import shutil
import subprocess
import time
from contextlib import contextmanager
from io import BytesIO
from operator import attrgetter
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Generator
from unittest import mock, TestCase

import image_to_pdf
import requests
from PIL import Image, ImageChops, PdfParser
from pypdf import PdfReader


DATA_PATH = Path(__file__).parent / "data"


class BaseTestCase(TestCase):
    @contextmanager
    def load_image(self, name: str = "antartica-3427135_640.jpg") -> Generator[Image.Image, None, None]:
        with Image.open(DATA_PATH / name) as image:
            yield image

    @contextmanager
    def load_image_from_url(self, url: str, suffix: str = ".png") -> Generator[Image.Image, None, None]:
        response = requests.get(url)
        self.assertEqual(200, response.status_code)
        with NamedTemporaryFile(suffix=suffix) as fd:
            fd.write(response.content)
            fd.seek(0)
            with self.load_image(fd.name) as image:
                yield image

    def get_size(self, path: Path) -> int:
        return path.stat().st_size

    def assert_size(self, path: Path, lower: int, upper: int) -> None:
        size = self.get_size(path)
        self.assertLess(lower, size)
        self.assertGreater(upper, size)

    def assert_images(self, expected: Image.Image, actual: Image.Image, threshold: float = 0.01, mode: str | None = None) -> None:
        self.assertEqual(expected.size, actual.size)
        self.assertEqual(mode or expected.mode, actual.mode)

        difference = ImageChops.difference(expected, actual)
        pixels = list(difference.getdata())
        if isinstance(pixels[0], tuple):
            no_diff_value = tuple([0] * len(pixels[0]))
            diff_count = sum(1 if x != no_diff_value else 0 for x in pixels)
        else:
            diff_count = sum(pixels)
        relative_difference = sum(expected.size) / diff_count
        self.assertGreaterEqual(threshold, relative_difference)

    def assert_page_count(self, path: Path, expected: int) -> None:
        reader = PdfReader(path)
        self.assertEqual(expected, len(reader.pages))

    def save_as_pdf(self, image: Image.Image, save_all: bool = False, check_size: bool = True, **kwargs: Any) -> Path:
        method = image_to_pdf.save_all if save_all else image_to_pdf.save

        with NamedTemporaryFile(suffix=".pdf", delete=False) as _file:
            outfile = Path(_file.name)
        self.addCleanup(outfile.unlink)
        with outfile.open(mode="wb") as fp:
            method(im=image, fp=fp, filename=outfile.name, **kwargs)

        self.assertTrue(outfile.is_file())
        self.assertLess(0, self.get_size(outfile))
        with PdfParser.PdfParser(str(outfile)) as pdf:
            if kwargs.get("append_images", False) or kwargs.get("append", False):
                self.assertLess(1, len(pdf.pages))
            else:
                self.assertLess(0, len(pdf.pages))

        if check_size:
            contents = outfile.read_bytes()
            size = tuple(map(float, contents.split(b"/MediaBox [ 0 0 ")[1].split(b"]")[0].split()))
            self.assertEqual(image.size, size)
        return outfile


class ConversionTestCase(BaseTestCase):
    def test_image_mode_1__has_libtiff(self):
        self.assertTrue(image_to_pdf.features.check("libtiff"))
        with self.load_image() as image:
            image = image.convert("1")
            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("antartica-3427135_640_1_libtiff.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 80000, 100000)

    def test_image_mode_1__no_libtiff(self):
        with mock.patch.object(image_to_pdf.features, "check", return_value=False) as check_mock:
            with self.load_image() as image:
                image = image.convert("1")
                outfile = self.save_as_pdf(image)
                # DATA_PATH.joinpath("antartica-3427135_640_1.pdf").write_bytes(outfile.read_bytes())
                self.assert_size(outfile, 160000, 180000)
            check_mock.assert_called_once_with("libtiff")

    def test_image_mode_l(self):
        with self.load_image() as image:
            image = image.convert("L")
            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("antartica-3427135_640_l.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 19000, 20000)

    def test_image_mode_la(self):
        for prefix, size_range in [
            ("black", (50000, 60000)),
            ("orange", (60000, 70000)),
            ("white", (40000, 50000)),
        ]:
            with self.subTest(prefix=prefix):
                with self.load_image(DATA_PATH / f"{prefix}_text_on_transparent_background.png") as image:
                    image = image.convert("LA")
                    outfile = self.save_as_pdf(image)
                    # DATA_PATH.joinpath(f"{prefix}_text_on_transparent_background_la.pdf").write_bytes(outfile.read_bytes())
                    self.assert_size(outfile, *size_range)

    def test_image_mode_p(self):
        with self.load_image() as image:
            image = image.convert("P")
            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("antartica-3427135_640_p.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 555000, 556000)

    def test_image_mode_p__with_transparency(self):
        with self.load_image_from_url("https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/images/pil123p.png") as image:
            self.assertEqual("P", image.mode)
            self.assertIsInstance(image.info["transparency"], bytes)

            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("pil123p_pa.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 55000, 56000)
            self.assertIn(b"\n/SMask ", outfile.read_bytes())

    def test_image_mode_rgb(self):
        with self.load_image() as image:
            self.assertEqual("RGB", image.mode)
            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("antartica-3427135_640_rgb.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 22000, 23000)

    def test_image_mode_rgba(self):
        for prefix, size_range in [
            ("black", (37000, 38000)),
            ("orange", (50000, 51000)),
            ("white", (30000, 40000)),
        ]:
            with self.subTest(prefix=prefix):
                with self.load_image(DATA_PATH / f"{prefix}_text_on_transparent_background.png") as image:
                    self.assertEqual("RGBA", image.mode)
                    outfile = self.save_as_pdf(image)
                    # DATA_PATH.joinpath(f"{prefix}_text_on_transparent_background_rgba.pdf").write_bytes(outfile.read_bytes())
                    self.assert_size(outfile, *size_range)

    def test_image_mode_cmyk(self):
        with self.load_image() as image:
            image = image.convert("CMYK")
            outfile = self.save_as_pdf(image)
            # DATA_PATH.joinpath("antartica-3427135_640_cmyk.pdf").write_bytes(outfile.read_bytes())
            self.assert_size(outfile, 59000, 61000)

    def test_image_mode_hsv(self):
        with self.load_image() as image:
            image = image.convert("HSV")
            with self.assertRaisesRegex(expected_exception=ValueError, expected_regex=r"^cannot save mode HSV$"):
                self.save_as_pdf(image)


class RecoveryTestCase(BaseTestCase):
    def assert_image_mode_rgba(self, check_method):
        for prefix in ["black", "orange", "white"]:
            with self.subTest(prefix=prefix):
                with self.load_image(DATA_PATH / f"{prefix}_text_on_transparent_background.png") as image:
                    self.assertEqual("RGBA", image.mode)
                    outfile = self.save_as_pdf(image)
                    check_method(image, outfile)

    def test_image_mode_rgba__pypdf(self):
        def check(image: Image.Image, outfile: Path):
            reader = PdfReader(outfile)
            new_image = reader.pages[0].images[0].image
            # new_image.save(DATA_PATH.joinpath(prefix + ".png"))
            # TODO: They appear to be visually identical, but their size differs quite a bit. Why?
            self.assert_images(image, new_image, threshold=0.08616)

        self.assert_image_mode_rgba(check)

    def test_image_mode_rgba__pdftocairo(self):
        def check(image: Image.Image, outfile: Path):
            with NamedTemporaryFile(suffix=".png", delete=False) as _file:
                png_path = Path(_file.name)
            self.addCleanup(png_path.unlink)
            # Resolution of 72 due to using the same value during writing the PDF file.
            result = subprocess.run(
                [shutil.which("pdftocairo"), "-png", "-singlefile", "-r", "72", outfile, "-"],
                stdout=subprocess.PIPE,
            )
            self.assertEqual(0, result.returncode)
            png_path.write_bytes(result.stdout)
            with Image.open(png_path) as new_image:
                # Extracted with white background.
                with self.assertRaisesRegex(expected_exception=ValueError, expected_regex=r"^images do not match$"):
                    self.assert_images(image, new_image, threshold=0.0, mode="RGB")

        self.assert_image_mode_rgba(check)

    def test_image_mode_rgba__pdfimages(self):
        def check(image: Image.Image, outfile: Path):
            with TemporaryDirectory() as directory:
                result = subprocess.run(
                    [shutil.which("pdfimages"), "-png", outfile, f"{directory}/out"],
                )
                self.assertEqual(0, result.returncode)
                directory = Path(directory)
                # Image and mask extracted separately.
                self.assertEqual({"out-000.png", "out-001.png"}, set(map(attrgetter("name"), directory.glob("*"))))

        self.assert_image_mode_rgba(check)

    def test_image_mode_rgba__mutool(self):
        def check(image: Image.Image, outfile: Path):
            with TemporaryDirectory() as directory:
                result = subprocess.run(
                    [shutil.which("mutool"), "extract", "-a", outfile],
                    cwd=directory,
                    stdout=subprocess.PIPE,
                )
                self.assertEqual(0, result.returncode)
                directory = Path(directory)
                # Image and mask extracted separately.
                self.assertEqual({"image-0001.jpg", "image-0002.png"}, set(map(attrgetter("name"), directory.glob("*"))))
                with Image.open(Path(directory, "image-0002.png")) as new_image:
                    self.assert_images(image, new_image, threshold=0.002)

        self.assert_image_mode_rgba(check)


class UpstreamTestCase(BaseTestCase):
    def test_resolution(self):
        for resolution, expected_size in [
            (100, (460.8, 307.44)),
            (150, (307.2, 204.96)),
        ]:
            with self.subTest(resolution=resolution):
                with self.load_image() as image:
                    path = self.save_as_pdf(image, resolution=resolution, check_size=False)
                contents = path.read_bytes()
                size = tuple(map(float, contents.split(b"stream\nq ")[1].split(b" 0 0 cm")[0].split(b" 0 0 ")))
                self.assertEqual(expected_size, size)

                size = tuple(map(float, contents.split(b"/MediaBox [ 0 0 ")[1].split(b"]")[0].split()))
                self.assertEqual(expected_size, size)

    def test_dpi(self):
        for kwargs, expected_size in [
            ({}, (614.4, 204.96)),
            ({"resolution": 200}, (614.4, 204.96)),
        ]:
            with self.subTest(kwargs=kwargs):
                with self.load_image() as image:
                    path = self.save_as_pdf(image, dpi=(75, 150), check_size=False, **kwargs)
                contents = path.read_bytes()
                size = tuple(map(float, contents.split(b"stream\nq ")[1].split(b" 0 0 cm")[0].split(b" 0 0 ")))
                self.assertEqual(expected_size, size)

                size = tuple(map(float, contents.split(b"/MediaBox [ 0 0 ")[1].split(b"]")[0].split()))
                self.assertEqual(expected_size, size)

    def test_save_all(self):
        # Single frame image.
        with self.load_image() as image:
            outfile = self.save_as_pdf(image, save_all=True)
            self.assert_page_count(outfile, 1)

        # Multiframe image.
        with self.load_image_from_url("https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/images/dispose_bgnd.gif", suffix=".gif") as image:
            outfile = self.save_as_pdf(image, save_all=True)
            self.assert_page_count(outfile, 5)

        # Append images.
        # Please note this test adds a page too much and the corresponding functionality only
        # works correctly when overwriting the default `PdfImagePlugin`.
        with self.load_image() as image:
            images = [image]
            with outfile.open(mode="r+b") as fd:
                image_to_pdf.save_all(image.copy(), fd, outfile.name, append_images=images)
            self.assert_page_count(outfile, 7)

        # Test appending using a generator.
        # Please note this test adds a page too much and the corresponding functionality only
        # works correctly when overwriting the default `PdfImagePlugin`.
        with self.load_image() as image:

            def image_generator() -> Generator[Image.Image, None, None]:
                yield image.copy()
                yield image.copy()

            with outfile.open(mode="r+b") as fd:
                image_to_pdf.save_all(image.copy(), fd, outfile.name, append_images=image_generator())
            self.assert_page_count(outfile, 10)

        # Append PNG images.
        # Please note this test adds a page too much and the corresponding functionality only
        # works correctly when overwriting the default `PdfImagePlugin`.
        with self.load_image("black_text_on_transparent_background.png") as image:
            with outfile.open(mode="r+b") as fd:
                image_to_pdf.save_all(image.copy(), fd, outfile.name, append_images=[image])
            self.assert_page_count(outfile, 12)

    def test_multiframe_normal_save(self):
        with self.load_image_from_url("https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/images/dispose_bgnd.gif", suffix=".gif") as image:
            outfile = self.save_as_pdf(image)
            self.assert_page_count(outfile, 1)

    def test_pdf_open(self):
        # Fail on a buffer full of null bytes.
        with self.assertRaisesRegex(expected_exception=PdfParser.PdfFormatError, expected_regex=r"^trailer end not found$"):
            PdfParser.PdfParser(buf=bytearray(65536))

        # Make an empty PDF object
        with PdfParser.PdfParser() as empty_pdf:
            self.assertEqual(0, len(empty_pdf.pages))
            self.assertEqual(0, len(empty_pdf.info))
            self.assertFalse(empty_pdf.should_close_buf)
            self.assertFalse(empty_pdf.should_close_file)

        # Make a PDF file.
        with self.load_image() as image:
            pdf_filename = self.save_as_pdf(image)

        # Open the PDF file.
        with PdfParser.PdfParser(filename=pdf_filename) as pdf:
            self.assertEqual(1, len(pdf.pages))
            self.assertTrue(pdf.should_close_buf)
            self.assertTrue(pdf.should_close_file)

        # Read a PDF file from a buffer with a non-zero offset.
        with open(pdf_filename, "rb") as f:
            content = b"xyzzy" + f.read()
        with PdfParser.PdfParser(buf=content, start_offset=5) as pdf:
            self.assertEqual(1, len(pdf.pages))
            self.assertFalse(pdf.should_close_buf)
            self.assertFalse(pdf.should_close_file)

        # Read a PDF file from an already open file.
        with open(pdf_filename, "rb") as f:
            with PdfParser.PdfParser(f=f) as pdf:
                self.assertEqual(1, len(pdf.pages))
                self.assertTrue(pdf.should_close_buf)
                self.assertFalse(pdf.should_close_file)

    def assert_pdf_pages_consistency(self, pdf: PdfParser.PdfParser) -> None:
        pages_info = pdf.read_indirect(pdf.pages_ref)
        self.assertNotIn(b"Parent", pages_info)
        self.assertIn(b"Kids", pages_info)
        kids_not_used = pages_info[b"Kids"]
        for page_ref in pdf.pages:
            while True:
                if page_ref in kids_not_used:
                    kids_not_used.remove(page_ref)
                page_info = pdf.read_indirect(page_ref)
                self.assertIn(b"Parent", page_info)
                page_ref = page_info[b"Parent"]
                if page_ref == pdf.pages_ref:
                    break
            self.assertEqual(pdf.pages_ref, page_info[b"Parent"])
        self.assertEqual([], kids_not_used)

    def test_pdf_append(self):
        # Make a PDF file.
        with self.load_image() as image:
            pdf_filename = self.save_as_pdf(image, producer="PdfParser")

        # Open it, check pages and info.
        with PdfParser.PdfParser(pdf_filename, mode="r+b") as pdf:
            self.assertEqual(1, len(pdf.pages))
            self.assertEqual(4, len(pdf.info))
            self.assertEqual(pdf_filename.stem, pdf.info.Title)
            self.assertEqual("PdfParser", pdf.info.Producer)
            self.assertIn(b"CreationDate", pdf.info)
            self.assertIn(b"ModDate", pdf.info)
            self.assert_pdf_pages_consistency(pdf)

            # Append some info.
            pdf.info.Title = "abc"
            pdf.info.Author = "def"
            pdf.info.Subject = "ghi\uABCD"
            pdf.info.Keywords = "qw)e\\r(ty"
            pdf.info.Creator = "hopper()"
            pdf.start_writing()
            pdf.write_xref_and_trailer()

        # Open it again, check pages and info again.
        with PdfParser.PdfParser(pdf_filename) as pdf:
            self.assertEqual(1, len(pdf.pages))
            self.assertEqual(8, len(pdf.info))
            self.assertEqual("abc", pdf.info.Title)
            self.assertIn(b"CreationDate", pdf.info)
            self.assertIn(b"ModDate", pdf.info)
            self.assert_pdf_pages_consistency(pdf)

        # Append two images.
        with self.load_image() as image:
            mode_cmyk = image.convert("CMYK")
            mode_p = image.convert("P")
            with pdf_filename.open(mode="r+b") as fd:
                image_to_pdf.save_all(mode_cmyk, fd, pdf_filename.name, append=True, append_images=[mode_p])

        # Open the PDF again, check pages and info again.
        with PdfParser.PdfParser(pdf_filename) as pdf:
            self.assertEqual(3, len(pdf.pages))
            self.assertEqual(8, len(pdf.info))
            self.assertEqual("abc", PdfParser.decode_text(pdf.info[b"Title"]))
            self.assertEqual("abc", pdf.info.Title)
            self.assertEqual("PdfParser", pdf.info.Producer)
            self.assertEqual("qw)e\\r(ty", pdf.info.Keywords)
            self.assertEqual("ghi\uABCD", pdf.info.Subject)
            self.assertIn(b"CreationDate", pdf.info)
            self.assertIn(b"ModDate", pdf.info)
            self.assert_pdf_pages_consistency(pdf)

    def test_pdf_info(self):
        # Make a PDF file.
        with self.load_image() as image:
            pdf_filename = self.save_as_pdf(
                image,
                "RGB",
                title="title",
                author="author",
                subject="subject",
                keywords="keywords",
                creator="creator",
                producer="producer",
                creationDate=time.strptime("2000", "%Y"),
                modDate=time.strptime("2001", "%Y"),
            )

        # Open it, check pages and info.
        with PdfParser.PdfParser(pdf_filename) as pdf:
            self.assertEqual(8, len(pdf.info))
            self.assertEqual("title", pdf.info.Title)
            self.assertEqual("author", pdf.info.Author)
            self.assertEqual("subject", pdf.info.Subject)
            self.assertEqual("keywords", pdf.info.Keywords)
            self.assertEqual("creator", pdf.info.Creator)
            self.assertEqual("producer", pdf.info.Producer)
            self.assertEqual(time.strptime("2000", "%Y"), pdf.info.CreationDate)
            self.assertEqual(time.strptime("2001", "%Y"), pdf.info.ModDate)
            self.assert_pdf_pages_consistency(pdf)

    def test_pdf_append_to_bytesio(self):
        with self.load_image() as image:
            f = BytesIO()
            image_to_pdf.save(image, f, "dummy.pdf", format="PDF")
            initial_size = len(f.getvalue())
            self.assertLess(0, initial_size)
            image = image.convert("P")
            f = BytesIO(f.getvalue())
            image_to_pdf.save(image, f, "dummy.pdf", format="PDF", append=True)
            self.assertLess(initial_size, len(f.getvalue()))


class OverwriteSaveContext:
    def __init__(self):
        self._original_save = Image.SAVE["PDF"]
        self._original_save_all = Image.SAVE_ALL["PDF"]

    def __enter__(self):
        Image.SAVE["PDF"] = image_to_pdf.save
        Image.SAVE_ALL["PDF"] = image_to_pdf.save_all

    def __exit__(self, type_, value, traceback):
        Image.SAVE["PDF"] = self._original_save
        Image.SAVE_ALL["PDF"] = self._original_save_all
        if type_:
            # Error.
            return
        return True


class IntegrationTestCase(BaseTestCase):
    def test_rgba(self):
        with self.load_image("black_text_on_transparent_background.png") as image:
            target = BytesIO()
            image.save(target, format="PDF")
            self.assertIn(b"/JPXDecode", target.getvalue())

            with OverwriteSaveContext():
                target = BytesIO()
                image.save(target, format="PDF")
                self.assertNotIn(b"/JPXDecode", target.getvalue())

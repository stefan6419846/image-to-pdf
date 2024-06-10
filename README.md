# Image to PDF

Convert images to PDF files, utilizing *Pillow*, while attempting to handle alpha channels in a suitable manner.

## About

I have always been looking for a good and reliable way to convert images to PDF files, while supporting images with alpha channels and avoiding undesired data loss.

My usual approach for converting images to PDF has been the implementation from *Pillow* as this would at least warn about data loss when handling alpha channels. Version 9.5.0 introduced the ability to convert RGBA images to PDF files as well by using JPEG2000/JPX images: [#6925](https://github.com/python-pillow/Pillow/pull/6925). But why do we need another library when *Pillow* apparently solved this problem some time ago?

During some tests, it turned out that neither *pdf.js* nor *Poppler*/*Cairo* would correctly render these PDF files: [#8074](https://github.com/python-pillow/Pillow/issues/8074). Due to *pdf.js* being my default PDF viewer for the web browser and *pdftocairo* my usual way to convert PDF files to thumbnails etc., this did not look right. Although *pdf.js* has fixed the bug in the meantime, it seems like JPX files with alpha channels are not handled sufficiently by all viewers, thus restricting the possible user base.

In the process of my report about the issues to *Pillow*, a pull request came up which would replace the alpha handling with SMasks: [#8097](https://github.com/python-pillow/Pillow/pull/8097). Unfortunately, it has been closed in the meantime since *pdf.js* fixed the bug. As this approach proved to be the most stable in my opinion, I decided to create an own package for it, while incorporating some basic feedback from user *sl2c* to not use `/DCTDecode` for RGBA images, but `/FlateDecode` instead. During testing, it turned out that *pypdf* would be able to recover the original image representation, even when the PDF had a white image on white background - this is just to make sure that ideally no data gets lost, although most of my usual RGBA images are indeed regular screenshots where removing the transparency altogether would not hurt, but this generally requires some more complex approaches to detect it.

Further alternatives I considered:

* Using `image.paste` through *Pillow* to copy the possibly transparent image onto a white background. This has the side effect of basically making all white areas of the original image unreadable if the background has been transparent.
* Using `pdfrwx`: I have not been able to recover the original image with its transparency in all cases. Additionally, this repository is neither packaged nor does it have any unit or integration tests. It depends on both NumPy and SciPy as well as *potrace* (GPL-2.0-or-later), being quite heavy and possibly introducing viral effects. *pdfrw*, another dependency, has been unmaintained for quite some time.

## Installation

You can install this package from PyPI:

```bash
python -m pip install image-to-pdf
```

## Usage

The main entry point is `image_to_pdf.save()`, which will convert one image to a PDF file by default. For all other functionality and some examples, I recommend you to have a look at the tests.

Additionally, the general API is compatible to the original `PIL.PdfImagePlugin`. Thus, you can configure this package to overwrite the original `PdfImagePlugin` functionality. See `IntegrationTestCase` for an example.

## License

This package is subject to the terms of the HPND license.

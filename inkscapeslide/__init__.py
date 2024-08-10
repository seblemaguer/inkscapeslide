#!/usr/bin/python
# -=- encoding: utf-8 -=-

"""
Author: Alexandre Bourget
Copyright (c) 2008: Alexandre Bourget
LICENSE: GPLv3

inkscapeslide is a simple tool to generate slides from inkscape files.

See --help for more.
"""

import lxml.etree
import sys
import os
import subprocess
import re
from optparse import OptionParser

def set_style(el, style, value):
    """
    Set the display: style, add it if it isn't there, don't touch the
    rest.
    """
    if re.search(r"%s: ?[a-zA-Z0-9.]*" % style, el.attrib["style"]):
        el.attrib["style"] = re.sub(
            r"(.*%s: ?)([a-zA-Z0-9.]*)(.*)" % style,
            r"\1%s\3" % value,
            el.attrib["style"],
        )
    else:
        el.attrib["style"] = "%s:%s;%s" % (style, value, el.attrib["style"])


def main():
    import warnings

    # HIDE DEPRECATION WARNINGS ONLY IN RELEASES. SHOW THEM IN DEV. TRUNKS
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # optparse setup
    usage = """
%prog [options] svgfilename

inkscapeslide is a simple tool to generate slides from inkscape files.

Create a 'content'-labeled layer and put a text box (no flowRect), with
each line looking like:

   background, layer1
   background, layer2
   background, layer2, layer3
   background, layer2 * 0.5, layer
   +layer4 * 0.5

Each name being the label of a layer. Lines starting with a '+' will add
the named layer to the layers of the preceding line, creating
incremental display (note there must be no whitespace before '+')

The opacity of a layer can be changed by adding '*[0., 1]' after the
layer name. The opacity must be between 0 and 1. Example:

    background, mylayer * 0.5
    """
    parser = OptionParser(usage=usage)
    parser.add_option(
        "-i",
        "--imageexport",
        action="store_true",
        dest="imageexport",
        default=False,
        help="Use PNG files as export content",
    )
    parser.add_option(
        "--export-pdf",
        dest="export_pdf",
        default=None,
        type=str,
        help="The outputFile"
    )
    (options, args) = parser.parse_args()
    try:
        svg_filename = args[0]
    except IndexError:
        parser.print_help()
        sys.exit(1)


    output_file = "%s.pdf" % svg_filename.split(".svg")[0]
    if options.export_pdf is not None:
        output_file = options.export_pdf
    # if os.path.exists(output_file): # FIXME:
    #     sys.exit(0)

    # Load the file
    doc = lxml.etree.parse(svg_filename)

    # Get all layers
    ink_groupmode = "{http://www.inkscape.org/namespaces/inkscape}groupmode"
    w3c_svg_tag = "{http://www.w3.org/2000/svg}g"
    layers = [
        layer
        for layer in doc.getroot().iterdescendants(tag=w3c_svg_tag)
        if layer.attrib.get(ink_groupmode, False) == "layer"
    ]

    # inkscape names for certain things in the svg
    ink_label = "{http://www.inkscape.org/namespaces/inkscape}label"

    # Scan the 'content' layer
    content_layer = [
        layer
        for layer in layers
        if layer.attrib.get(ink_label, False).lower() == "content"
    ]
    if not content_layer:
        basename =  svg_filename.split(".svg")[0]
        cmd = f"inkscape --export-type=pdf -o {basename} {svg_filename}"
        if options.imageexport:
            cmd = f"inkscape -d 180 --export-type=png -o {basename} {svg_filename}"

        # Using subprocess to hide stdout
        subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).communicate()
        sys.exit(0)

    content = content_layer[0]

    # Find the text stuff, everything starting with SLIDE:
    #   take all the layer names separated by ','..
    ink_tspan = "{http://www.w3.org/2000/svg}text/{http://www.w3.org/2000/svg}tspan"
    preslides = [x.text for x in content.findall(ink_tspan) if x.text]

    if not bool(preslides):
        print(
            "Make sure you have a text box (with no flowRect) in the "
            "'content' layer, and rerun this program."
        )
        sys.exit(1)

    # Get the initial style attribute and keep it
    orig_style = {}
    for layer in layers:
        label = layer.attrib.get(ink_label)
        if "style" not in layer.attrib:
            layer.set("style", "")
        # Save initial values
        orig_style[label] = layer.attrib["style"]

    # slides contains seq of [('layer', opacity), ('layer', opacity), ..]
    slides = []
    for slide in preslides:
        if slide:
            if slide.startswith("+"):
                slide = slide[1:]
                sl_layers = slides[-1].copy()
            else:
                sl_layers = {}

            for layer in slide.split(","):
                elements = layer.strip().split("*")
                name = elements[0].strip()
                opacity = None
                if len(elements) == 2:
                    opacity = float(elements[1].strip())
                sl_layers[name] = {"opacity": opacity}
            slides.append(sl_layers)

    pdfslides = []
    for i, slide_layers in enumerate(slides):
        for l in layers:
            labels_path = set()
            cur_n = l
            while (cur_n is not None):
                label = cur_n.attrib.get(ink_label)
                if label is not None:
                    labels_path.add(label)
                cur_n = cur_n.getparent()

            # Set display mode to original
            label = l.attrib.get(ink_label)
            l.set("style", orig_style[label])

            # Don't show it by default...
            set_style(l, "display", "none")

            wanted_labels = labels_path.intersection(slide_layers)
            if wanted_labels:
                if len(wanted_labels) > 1:
                    raise Exception(f"There seems to have multiple layers matching the one we want: {len(wanted_labels)}")
                label = wanted_labels.pop()
                set_style(l, "display", "inline")
                opacity = slide_layers[label]["opacity"]
                if opacity:
                    set_style(l, "opacity", str(opacity))

        svgslide = os.path.abspath(
            os.path.join(os.curdir, "%s.p%d.svg" % (svg_filename, i))
        )
        pdfslide = os.path.abspath(
            os.path.join(os.curdir, "%s.p%d.pdf" % (svg_filename, i))
        )

        # Use the correct extension if using images
        if options.imageexport:
            pdfslide = os.path.abspath(
                os.path.join(os.curdir, ".inkscapeslide_%s.p%05d.png" % (svg_filename, i))
            )

        # Write the XML to file, "wireframes.p1.svg"
        f = open(svgslide, "wb")
        f.write(lxml.etree.tostring(doc))
        f.close()

        # Determine whether to export pdf's or images (e.g. inkscape -A versus
        # inkscape -e)
        cmd = "inkscape --export-type=pdf -o %s %s" % (pdfslide, svgslide)
        if options.imageexport:
            cmd = "inkscape -d 180 --export-type=png -o %s %s" % (pdfslide, svgslide)

        # Using subprocess to hide stdout
        subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).communicate()
        os.unlink(svgslide)
        pdfslides.append(pdfslide)

        print("Generated page %d." % (i + 1))

    joinedpdf = False
    output_file = "%s.pdf" % svg_filename.split(".svg")[0]
    outputDir = os.path.dirname(output_file)
    print("Output file %s" % output_file)

    if options.imageexport:
        # Use ImageMagick to combine the PNG files into a PDF
        if not os.system("which convert > /dev/null"):
            print("Using 'convert' to join PNG's")
            pngPath = os.path.join(outputDir, ".inkscapeslide_*.png")
            proc = subprocess.Popen(
                "convert %s -resample 180 %s" % (pngPath, output_file),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # See if the command succeeded
            stdout_value, stderr_value = proc.communicate()
            if proc.returncode:
                print("\nERROR: convert command failed:")
                print(stderr_value)
            else:
                joinedpdf = True
        else:
            print("Please install ImageMagick to provide the 'convert' utility")
    else:
        # Join PDFs
        has_pyPdf = False
        try:
            import pyPdf

            has_pyPdf = True
        except:
            pass

        if has_pyPdf:
            print("Using 'pyPdf' to join PDFs")
            output = pyPdf.PdfFileWriter()
            inputfiles = []
            for slide in pdfslides:
                inputstream = file(slide, "rb")
                inputfiles.append(inputstream)
                input = pyPdf.PdfFileReader(inputstream)
                output.addPage(input.getPage(0))
            outputStream = file(output_file, "wb")
            output.write(outputStream)
            outputStream.close()
            for f in inputfiles:
                f.close()
            joinedpdf = True

        # Verify pdfjoin exists in PATH
        elif not os.system("which pdfjoin > /dev/null"):
            # In the end, run: pdfjoin wireframes.p*.pdf -o Wireframes.pdf
            print("Using 'pdfsam' to join PDFs")
            os.system(
                "pdfjoin --outfile %s.pdf %s"
                % (svg_filename.split(".svg")[0], " ".join(pdfslides))
            )
            joinedpdf = True

        # Verify pdftk exists in PATH
        elif not os.system("which pdftk > /dev/null"):
            # run: pdftk in1.pdf in2.pdf cat output Wireframes.pdf
            print("Using 'pdftk' to join PDFs")
            os.system(
                "pdftk %s cat output %s"
                % (" ".join(pdfslides), output_file)
            )
            joinedpdf = True
        else:
            print(
                "Please install pdfjam, pdftk or install the 'pyPdf'"
                "python package, to join PDFs."
            )

    # Clean up
    if joinedpdf:
        for pdfslide in pdfslides:
            os.unlink(pdfslide)

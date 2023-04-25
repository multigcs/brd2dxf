import argparse
import math

import ezdxf
import shapely
import xmltodict
from ezdxf import zoom
from shapely.geometry import Polygon
from shapely.ops import unary_union

selections = {
    "top_copper": {"color": 1, "layers": ["Top"]},
    "bottom_copper": {"color": 5, "layers": ["Bottom"]},
    "all_drills": {"color": 2, "layers": ["Drills"]},
    "top_print": {"color": 9, "layers": ["tDocu", "tPlace"]},
    "bottom_print": {"color": 9, "layers": ["bDocu", "bPlace"]},
    "top_glue": {"color": 7, "layers": ["tGlue"]},
    "bottom_glue": {"color": 7, "layers": ["bGlue"]},
    "board": {"color": 3, "layers": ["Dimension"]},
    "top_smd": {"color": 3, "layers": ["TopSMD"]},
    "bottom_smd": {"color": 3, "layers": ["BottomSMD"]},
}

dxfcolors = {
    "0": 0,  #: (0.0, 0.0, 0.0, "black"),
    "Top": 1,  #: (1.0, 0.0, 0.0, "red"),
    "Drills": 2,  #: (1.0, 1.0, 0.0, "yellow"),
    "Pads": 3,  #: (0.0, 1.0, 0.0, "green"),
    "Vias": 3,  #: (0.0, 1.0, 0.0, "green"),
    "Dimension": 4,  #: (0.0, 1.0, 1.0, "cyan"),
    "Bottom": 5,  #: (0.0, 0.0, 1.0, "blue"),
    "6": 6,  #: (1.0, 0.0, 1.0, "magenta"),
    "tDocu": 7,  #: (1.0, 1.0, 1.0, "white"),
    "bDocu": 7,  #: (1.0, 1.0, 1.0, "white"),
    "tKeepout": 8,  #: (0.2549019607843137, 0.2549019607843137, 0.2549019607843137, "gray"),
    "bKeepout": 8,  #: (0.2549019607843137, 0.2549019607843137, 0.2549019607843137, "gray"),
    "8": 8,  #: (0.2549019607843137, 0.2549019607843137, 0.2549019607843137, "gray"),
    "tPlace": 9,  #: (0.5019607843137255, 0.5019607843137255, 0.5019607843137255, "lightgray"),
    "bPlace": 9,  #: (0.5019607843137255, 0.5019607843137255, 0.5019607843137255, "lightgray"),
}


layerdata = {}
layers_in_use = set()
polygons = {}
polygon_areas = {}
signals2pads = {}
plain = []


def angle_of_line(p_1, p_2):
    """gets the angle of a single line."""
    return math.atan2(p_2[1] - p_1[1], p_2[0] - p_1[0])


def rotate_point(
    origin_x: float, origin_y: float, point_x: float, point_y: float, angle: float
) -> tuple:
    new_x = (
        origin_x
        + math.cos(angle) * (point_x - origin_x)
        - math.sin(angle) * (point_y - origin_y)
    )
    new_y = (
        origin_y
        + math.sin(angle) * (point_x - origin_x)
        + math.cos(angle) * (point_y - origin_y)
    )
    return (new_x, new_y)


def draw_circle(center, radius, steps=18):
    """draws an circle"""
    points = []
    step = math.pi * 2 / steps
    angle = -step / 2
    while angle < math.pi * 2 + step:
        p_x = center[0] + radius * math.sin(angle)
        p_y = center[1] - radius * math.cos(angle)
        points.append((p_x, p_y))
        angle += step
    return points


def signal_add_wire(msp, wire, signal_name):
    x1 = float(wire["@x1"])
    y1 = float(wire["@y1"])
    x2 = float(wire["@x2"])
    y2 = float(wire["@y2"])
    lw = float(wire["@width"])
    layer = layerdata[wire["@layer"]]["@name"]
    color = layerdata[wire["@layer"]]["@fill"]
    radius = lw / 2
    p_from = (x1, y1)
    p_to = (x2, y2)
    line_angle = angle_of_line(p_from, p_to)

    if layer not in polygons:
        polygons[layer] = []

    polygons[layer].append(Polygon(draw_circle((x1, y1), radius)))
    polygons[layer].append(Polygon(draw_circle((x2, y2), radius)))
    x_out_from = p_from[0] + radius * math.sin(line_angle)
    y_out_from = p_from[1] - radius * math.cos(line_angle)
    x_in_from = p_from[0] + radius * math.sin(line_angle + math.pi)
    y_in_from = p_from[1] - radius * math.cos(line_angle + math.pi)
    x_out_to = p_to[0] + radius * math.sin(line_angle)
    y_out_to = p_to[1] - radius * math.cos(line_angle)
    x_in_to = p_to[0] + radius * math.sin(line_angle + math.pi)
    y_in_to = p_to[1] - radius * math.cos(line_angle + math.pi)
    polygons[layer].append(
        Polygon(
            [
                (x_in_from, y_in_from),
                (x_in_to, y_in_to),
                (x_out_to, y_out_to),
                (x_out_from, y_out_from),
            ]
        )
    )


def signal_add_via(msp, via, signal_name):
    x = float(via["@x"])
    y = float(via["@y"])
    drill = float(via["@drill"])
    size = 1
    if "@diameter" in via:
        size = float(via["@diameter"])
    elif "@extent" in via:
        size = drill / 2 + float(via["@extent"].split("-")[1]) / 100
    msp.add_circle((x, y), drill / 2, dxfattribs={"layer": "Drills"})
    layers_in_use.add("Drills")

    for layer in ["Top", "Bottom"]:
        area_name = f"{layer}_{signal_name}"
        if area_name not in polygon_areas:  # TODO: check if inside
            if layer not in polygons:
                polygons[layer] = []
            polygons[layer].append(Polygon(draw_circle((x, y), size)))


def signal_add_polygon(msp, polygon, signal_name):
    lw = float(polygon["@width"])
    layer = layerdata[polygon["@layer"]]["@name"]
    color = layerdata[polygon["@layer"]]["@color"]
    last = (
        float(polygon["vertex"][-1]["@x"]),
        float(polygon["vertex"][-1]["@y"]),
    )

    points = []
    for point in polygon["vertex"]:
        x = float(point["@x"])
        y = float(point["@y"])
        points.append((x, y))

    area_name = f"{layer}_{signal_name}"
    if area_name not in polygon_areas:
        polygon_areas[area_name] = []

    polygon_areas[area_name].append(points)

    layer_org = layer

    layer = f"{layer_org}Poly"
    if layer not in polygons:
        polygons[layer] = []

    bigpoly = Polygon(points)
    frame = Polygon(plain)

    clipped_polygon = bigpoly.intersection(frame)
    polygons[layer].append(clipped_polygon)


def package_add_pad(
    msp,
    pad,
    layer,
    element_name,
    element_x,
    element_y,
    element_rot_angle,
    element_mirror,
):
    layer = "Top"
    if layer not in polygons:
        polygons[layer] = []
    layer = "Bottom"
    if layer not in polygons:
        polygons[layer] = []

    shape = pad.get("@shape")
    if shape not in ["long", "octagon"]:
        print("Unsupported shape:", shape)

    px = float(pad["@x"])
    py = float(pad["@y"])
    if element_mirror:
        px *= -1

    if "@rot" in pad:
        rot = pad["@rot"]
        rot_dir = rot[0]
        rot_angle = float(rot[1:])
    else:
        rot = ""
        rot_dir = "R"
        rot_angle = 0.0

    if rot_angle and False:
        x = px
        y = py
        (x, y) = rotate_point(0.0, 0.0, x, y, rot_angle * math.pi / 180)
        x = element_x + x
        y = element_y + y
    else:
        x = element_x + px
        y = element_y + py

    if element_rot_angle:
        (x, y) = rotate_point(
            element_x,
            element_y,
            x,
            y,
            element_rot_angle * math.pi / 180,
        )
    drill = float(pad["@drill"])
    msp.add_circle(
        (x, y),
        drill / 2,
        dxfattribs={"layer": "Drills"},
    )
    layers_in_use.add("Drills")
    if "@diameter" in pad:
        # round and octagon shape

        for layer in ["Top", "Bottom"]:
            signal_name = ""
            for sname in signals2pads:
                for spad in signals2pads[sname]:
                    if (
                        pad["@name"] == spad["@pad"]
                        and element_name == spad["@element"]
                    ):
                        signal_name = sname
                        break
            area_name = f"{layer}_{signal_name}"
            if area_name not in polygon_areas:  # TODO: check if inside

                diameter = float(pad["@diameter"])

                if shape == "octagon":
                    polygons[layer].append(
                        Polygon(draw_circle((x, y), diameter / 2, 8))
                    )
                else:
                    polygons[layer].append(Polygon(draw_circle((x, y), diameter / 2)))
    else:
        # long shape

        pad_size = drill / 3 * 2
        x1 = x + pad_size
        y1 = y
        x2 = x - pad_size
        y2 = y
        if rot_angle:
            (x1, y1) = rotate_point(x, y, x1, y1, rot_angle * math.pi / 180)
            (x2, y2) = rotate_point(x, y, x2, y2, rot_angle * math.pi / 180)
        if element_rot_angle and rot:
            (x1, y1) = rotate_point(
                x,
                y,
                x1,
                y1,
                element_rot_angle * math.pi / 180,
            )
            (x2, y2) = rotate_point(
                x,
                y,
                x2,
                y2,
                element_rot_angle * math.pi / 180,
            )
        for layer in ["Top", "Bottom"]:
            signal_name = ""
            for sname in signals2pads:
                for spad in signals2pads[sname]:
                    if (
                        pad["@name"] == spad["@pad"]
                        and element_name == spad["@element"]
                    ):
                        signal_name = sname
                        break
            area_name = f"{layer}_{signal_name}"
            if area_name not in polygon_areas:  # TODO: check if inside

                polygons[layer].append(Polygon(draw_circle((x1, y1), pad_size)))
                polygons[layer].append(Polygon(draw_circle((x2, y2), pad_size)))
        x1 = x + pad_size
        y1 = y - pad_size
        x2 = x - pad_size
        y2 = y - pad_size
        if rot_angle:
            (x1, y1) = rotate_point(x, y, x1, y1, rot_angle * math.pi / 180)
            (x2, y2) = rotate_point(x, y, x2, y2, rot_angle * math.pi / 180)
        if element_rot_angle and rot:
            (x1, y1) = rotate_point(
                x,
                y,
                x1,
                y1,
                element_rot_angle * math.pi / 180,
            )
            (x2, y2) = rotate_point(
                x,
                y,
                x2,
                y2,
                element_rot_angle * math.pi / 180,
            )
        x3 = x + pad_size
        y3 = y + pad_size
        x4 = x - pad_size
        y4 = y + pad_size
        if rot_angle:
            (x3, y3) = rotate_point(x, y, x3, y3, rot_angle * math.pi / 180)
            (x4, y4) = rotate_point(x, y, x4, y4, rot_angle * math.pi / 180)
        if element_rot_angle and rot:
            (x3, y3) = rotate_point(
                x,
                y,
                x3,
                y3,
                element_rot_angle * math.pi / 180,
            )
            (x4, y4) = rotate_point(
                x,
                y,
                x4,
                y4,
                element_rot_angle * math.pi / 180,
            )
        for layer in ["Top", "Bottom"]:
            signal_name = ""
            for sname in signals2pads:
                for spad in signals2pads[sname]:
                    if (
                        pad["@name"] == spad["@pad"]
                        and element_name == spad["@element"]
                    ):
                        signal_name = sname
                        break
            area_name = f"{layer}_{signal_name}"
            if area_name not in polygon_areas:  # TODO: check if inside
                polygons[layer].append(
                    Polygon(
                        [
                            (x1, y1),
                            (x2, y2),
                            (x4, y4),
                            (x3, y3),
                        ]
                    )
                )


def package_add_circle(
    msp,
    circle,
    layer,
    element_name,
    element_x,
    element_y,
    element_rot_angle,
    element_mirror,
):
    x = element_x + float(circle["@x"])
    y = element_y + float(circle["@y"])
    radius = float(circle["@radius"])
    lw = float(circle["@width"])
    layer = layerdata[circle["@layer"]]["@name"]
    color = layerdata[circle["@layer"]]["@fill"]
    if element_rot_angle:
        (x, y) = rotate_point(
            element_x,
            element_y,
            x,
            y,
            element_rot_angle * math.pi / 180,
        )
    msp.add_circle((x, y), radius, dxfattribs={"layer": layer})
    layers_in_use.add(layer)


def package_add_wire(
    msp,
    wire,
    layer,
    element_name,
    element_x,
    element_y,
    element_rot_angle,
    element_mirror,
):
    x1 = element_x + float(wire["@x1"])
    x2 = element_x + float(wire["@x2"])
    y1 = element_y + float(wire["@y1"])
    y2 = element_y + float(wire["@y2"])
    lw = float(wire["@width"])
    layer = layerdata[wire["@layer"]]["@name"]
    color = layerdata[wire["@layer"]]["@fill"]
    if element_rot_angle:
        (x1, y1) = rotate_point(
            element_x,
            element_y,
            x1,
            y1,
            element_rot_angle * math.pi / 180,
        )
        (x2, y2) = rotate_point(
            element_x,
            element_y,
            x2,
            y2,
            element_rot_angle * math.pi / 180,
        )
    msp.add_line(
        (x1, y1),
        (x2, y2),
        dxfattribs={
            "layer": layer,
            "lineweight": lw * 100,
        },
    )
    layers_in_use.add(layer)


def package_add_rectangle(
    msp,
    rectangle,
    layer,
    element_name,
    element_x,
    element_y,
    element_rot_angle,
    element_mirror,
):
    x1 = element_x + float(rectangle["@x1"])
    x2 = element_x + float(rectangle["@x2"])
    y1 = element_y + float(rectangle["@y1"])
    y2 = element_y + float(rectangle["@y2"])
    layer = layerdata[rectangle["@layer"]]["@name"]
    color = layerdata[rectangle["@layer"]]["@fill"]
    if element_rot_angle:
        (x1, y1) = rotate_point(
            element_x,
            element_y,
            x1,
            y1,
            element_rot_angle * math.pi / 180,
        )
        (x2, y2) = rotate_point(
            element_x,
            element_y,
            x2,
            y2,
            element_rot_angle * math.pi / 180,
        )
    msp.add_line(
        (x1, y1),
        (x1, y2),
        dxfattribs={"layer": layer},
    )
    msp.add_line(
        (x1, y2),
        (x2, y2),
        dxfattribs={"layer": layer},
    )
    msp.add_line(
        (x2, y2),
        (x2, y1),
        dxfattribs={"layer": layer},
    )
    msp.add_line(
        (x2, y1),
        (x1, y1),
        dxfattribs={"layer": layer},
    )
    layers_in_use.add(layer)


def package_add_smd(
    msp,
    smd,
    layer,
    element_name,
    element_x,
    element_y,
    element_rot_angle,
    element_mirror,
):
    x = element_x + float(smd["@x"])
    y = element_y + float(smd["@y"])
    dx = float(smd["@dx"])
    dy = float(smd["@dy"])
    x1 = x - dx / 2
    y1 = y - dy / 2
    x2 = x + dx / 2
    y2 = y + dy / 2
    if "@rot" in smd:
        rot = smd["@rot"]
        rot_dir = rot[0]
        rot_angle = float(rot[1:])
    else:
        rot = ""
        rot_dir = "R"
        rot_angle = 0.0
    if element_rot_angle:
        (x1, y1) = rotate_point(
            element_x,
            element_y,
            x1,
            y1,
            element_rot_angle * math.pi / 180,
        )
        (x2, y2) = rotate_point(
            element_x,
            element_y,
            x2,
            y2,
            element_rot_angle * math.pi / 180,
        )

    if rot_angle:
        cx = x1 + (x2 - x1) / 2
        cy = y1 + (y2 - y1) / 2
        (x1, y1) = rotate_point(
            cx,
            cy,
            x1,
            y1,
            rot_angle * math.pi / 180,
        )
        (x2, y2) = rotate_point(
            cx,
            cy,
            x2,
            y2,
            rot_angle * math.pi / 180,
        )

    signal_name = ""
    for sname in signals2pads:
        for spad in signals2pads[sname]:
            if smd["@name"] == spad["@pad"] and element_name == spad["@element"]:
                signal_name = sname
                break
    area_name = f"{layer}_{signal_name}"
    if area_name not in polygon_areas:  # TODO: check if inside

        if layer not in polygons:
            polygons[layer] = []

        polygons[layer].append(
            Polygon(
                [
                    (x1, y1),
                    (x1, y2),
                    (x2, y2),
                    (x2, y1),
                ]
            )
        )

    p_layer = f"{layer}SMD"
    if p_layer not in polygons:
        polygons[p_layer] = []
    polygons[p_layer].append(
        Polygon(
            [
                (x1, y1),
                (x1, y2),
                (x2, y2),
                (x2, y1),
            ]
        )
    )


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="brd file", type=str, default=None)
    parser.add_argument("--output", help="output file", type=str, default="")
    parser.add_argument(
        "--layer", help="selected layer", type=str, default=[], action="append"
    )
    parser.add_argument("--list", help="list layers", action="store_true")
    parser.add_argument("--simple", help="simplifyed layers", action="store_true")
    args = parser.parse_args()

    if args.simple and args.list:
        for layer in selections:
            print(layer)
        exit(0)

    if not args.output:
        args.output = f"{args.filename}.dxf"

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    doc.units = ezdxf.units.MM

    print(f"reading brd-file: {args.filename}")
    xmldata = open(args.filename, "r").read()
    xmldict = xmltodict.parse(xmldata)
    layers = xmldict["eagle"]["drawing"]["layers"]
    board = xmldict["eagle"]["drawing"]["board"]

    for layer in layers["layer"]:
        number = layer["@number"]
        # color = layer["@fill"]
        color = layer["@color"]
        name = layer["@name"]
        layerdata[number] = layer

        # if name in dxfcolors:
        #    color = dxfcolors[name]
        # doc.layers.add(name=name, color=int(color))

    if args.list:
        for layer in layers["layer"]:
            name = layer["@name"]
            print(name)
        exit(0)

    for wire in board["plain"]["wire"]:
        x1 = float(wire["@x1"])
        x2 = float(wire["@x2"])
        y1 = float(wire["@y1"])
        y2 = float(wire["@y2"])
        lw = float(wire["@width"])
        layer = layerdata[wire["@layer"]]["@name"]
        color = layerdata[wire["@layer"]]["@color"]
        msp.add_line(
            (x1, y1),
            (x2, y2),
            dxfattribs={"layer": layer, "lineweight": lw * 100},
        )
        layers_in_use.add(layer)
        plain.append((x1, y1))
        plain.append((x2, y2))

    for signal in board["signals"]["signal"]:
        signal_name = signal.get("@name", "")
        if "contactref" in signal:
            if isinstance(signal["contactref"], dict):
                signal["contactref"] = [signal["contactref"]]
            for contactref in signal["contactref"]:
                if signal_name not in signals2pads:
                    signals2pads[signal_name] = []
                signals2pads[signal_name].append(contactref)

        if "polygon" in signal:
            if isinstance(signal["polygon"], dict):
                signal["polygon"] = [signal["polygon"]]
            for polygon in signal["polygon"]:
                signal_add_polygon(msp, polygon, signal_name)

        if "via" in signal:
            if isinstance(signal["via"], dict):
                signal["via"] = [signal["via"]]
            for via in signal["via"]:
                signal_add_via(msp, via, signal_name)

        if "wire" in signal:
            if isinstance(signal["wire"], dict):
                signal["wire"] = [signal["wire"]]
            for wire in signal["wire"]:
                signal_add_wire(msp, wire, signal_name)

    for element in board["elements"]["element"]:
        element_name = element["@name"]
        element_x = float(element["@x"])
        element_y = float(element["@y"])
        layer = "Top"
        element_mirror = False
        element_rot_angle = 0
        if "@rot" in element:
            rotate = element["@rot"]
            if rotate[0] == "M":
                layer = "Bottom"
                element_mirror = True
                element_rot_angle = float(rotate[2:])
            else:
                element_rot_angle = float(rotate[1:])

        library_id = element["@library"]
        package_name = element["@package"]
        for library in board["libraries"]["library"]:
            if library["@name"] == library_id:
                if isinstance(library["packages"]["package"], dict):
                    library["packages"]["package"] = [library["packages"]["package"]]
                for package in library["packages"]["package"]:
                    if package["@name"] == package_name:
                        if "smd" in package:
                            if isinstance(package["smd"], dict):
                                package["smd"] = [package["smd"]]
                            for smd in package["smd"]:
                                package_add_smd(
                                    msp,
                                    smd,
                                    layer,
                                    element_name,
                                    element_x,
                                    element_y,
                                    element_rot_angle,
                                    element_mirror,
                                )

                        if "pad" in package:
                            pads = package["pad"]
                            if isinstance(pads, dict):
                                pads = [pads]
                            for pad in pads:
                                package_add_pad(
                                    msp,
                                    pad,
                                    layer,
                                    element_name,
                                    element_x,
                                    element_y,
                                    element_rot_angle,
                                    element_mirror,
                                )

                        if "rectangle" in package:
                            if isinstance(package["rectangle"], dict):
                                package["rectangle"] = [package["rectangle"]]
                            for rectangle in package["rectangle"]:
                                package_add_rectangle(
                                    msp,
                                    rectangle,
                                    layer,
                                    element_name,
                                    element_x,
                                    element_y,
                                    element_rot_angle,
                                    element_mirror,
                                )

                        if "wire" in package:
                            if isinstance(package["wire"], dict):
                                package["wire"] = [package["wire"]]
                            for wire in package["wire"]:
                                package_add_wire(
                                    msp,
                                    wire,
                                    layer,
                                    element_name,
                                    element_x,
                                    element_y,
                                    element_rot_angle,
                                    element_mirror,
                                )

                        if "circle" in package:
                            if isinstance(package["circle"], dict):
                                package["circle"] = [package["circle"]]
                            for circle in package["circle"]:
                                package_add_circle(
                                    msp,
                                    circle,
                                    layer,
                                    element_name,
                                    element_x,
                                    element_y,
                                    element_rot_angle,
                                    element_mirror,
                                )

    polygons_off = {}
    for polylayer in ["Top", "Bottom"]:
        if polylayer not in polygons_off:
            polygons_off[polylayer] = []
        for poly in polygons[polylayer]:
            polygons_off[polylayer].append(poly.buffer(0.1))

    # merge polygons per layer (signal mask)
    for polylayer in polygons_off:
        u = unary_union(polygons_off[polylayer])
        if not isinstance(u, shapely.geometry.multipolygon.MultiPolygon):
            u = [u]
        else:
            u = u.geoms
        for poly in u:
            points = list(poly.exterior.coords)
            last = points[-1]
            for p in points:
                msp.add_line(
                    last,
                    p,
                    dxfattribs={"layer": f"{polylayer}_inner", "color": 2},
                )
                layers_in_use.add(polylayer)
                last = p

    # merge polygons per layer (single signals)
    for polylayer in polygons:
        u = unary_union(polygons[polylayer])
        if not isinstance(u, shapely.geometry.multipolygon.MultiPolygon):
            u = [u]
        else:
            u = u.geoms
        for poly in u:
            points = list(poly.exterior.coords)
            if not points:
                continue
            last = points[-1]
            for p in points:
                msp.add_line(
                    last,
                    p,
                    dxfattribs={"layer": polylayer},
                )
                layers_in_use.add(polylayer)
                last = p

    for layer in layers["layer"]:
        number = layer["@number"]
        # color = layer["@fill"]
        color = layer["@color"]
        name = layer["@name"]
        layerdata[number] = layer
        if name in layers_in_use:
            if name in dxfcolors:
                color = dxfcolors[name]
            doc.layers.add(name=name, color=int(color))

    doc.layers.add(name="TopPoly", color=1)
    doc.layers.add(name="BottomPoly", color=5)

    doc.layers.add(name="TopSMD", color=1)
    doc.layers.add(name="BottomSMD", color=5)

    if args.simple:
        # combine layers
        for select in selections:
            doc.layers.add(name=select, color=selections[select]["color"])
        for entity in list(doc.entitydb.values()):
            if not entity.dxf.hasattr("layer"):
                continue
            found = False
            for select in selections:
                if entity.dxf.layer in selections[select]["layers"]:
                    entity.dxf.layer = select
                    found = True
            if not found:
                entity.destroy()

        # removing unused layers
        for layer in layers_in_use:
            if layer not in selections:
                doc.layers.remove(layer)

    # clean by selection
    if args.layer:
        # removing entity from unused layers
        for entity in doc.entitydb.values():
            if not entity.dxf.hasattr("layer"):
                continue

            if entity.dxf.layer not in args.layer:
                entity.destroy()

        # removing unused layers
        for layer in layers_in_use:
            if layer not in args.layer:
                doc.layers.remove(layer)

    for vport in doc.viewports.get_config("*Active"):  # type: ignore
        vport.dxf.grid_on = True
    zoom.extents(msp)  # type: ignore

    print(f"writing dxf-file: {args.output}")
    doc.saveas(args.output)

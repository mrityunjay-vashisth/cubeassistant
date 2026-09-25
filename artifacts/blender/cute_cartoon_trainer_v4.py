from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Callable

import bpy
from mathutils import Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cute_airplane import (  # noqa: E402
    add_beveled_cube,
    add_curve,
    add_cylinder,
    add_cylinder_between,
    add_uv_sphere,
    assign_material,
    hex_color,
    make_material,
    point_at,
    smooth,
)
from cute_airplane_detailed import add_torus, make_emissive_material  # noqa: E402


BLEND_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4.blend"
HERO_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4.png"
SIDE_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4_side.png"
FRONT_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4_front.png"
TOP_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4_top.png"
DETAIL_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4_detail.png"

STAGE = "final"
GROUND_Z = 0.0
WING_HALF_SPAN = 4.25
TAIL_HALF_SPAN = 1.55


# X points aft, Y points toward the left wing, and Z points upward.
# Extra stations are intentional around glazing boundaries, the wing carry-through,
# the landing-gear frame, and the empennage attachment.
FUSELAGE_STATIONS: list[tuple[float, float, float, float, float]] = [
    (-2.86, 1.70, 0.20, 0.22, 2.00),
    (-2.72, 1.70, 0.49, 0.46, 2.10),
    (-2.48, 1.70, 0.63, 0.58, 2.20),
    (-2.12, 1.71, 0.70, 0.64, 2.35),
    (-1.78, 1.73, 0.74, 0.68, 2.55),
    (-1.62, 1.75, 0.76, 0.72, 2.70),
    (-1.50, 1.76, 0.77, 0.76, 2.85),
    (-1.34, 1.77, 0.79, 0.84, 3.00),
    (-1.13, 1.78, 0.81, 0.89, 3.10),
    (-1.02, 1.78, 0.82, 0.90, 3.10),
    (-0.92, 1.78, 0.83, 0.90, 3.10),
    (-0.18, 1.78, 0.84, 0.89, 3.10),
    (-0.08, 1.78, 0.84, 0.89, 3.10),
    (0.04, 1.78, 0.83, 0.88, 3.05),
    (0.14, 1.78, 0.82, 0.87, 3.00),
    (0.58, 1.77, 0.78, 0.80, 2.85),
    (0.68, 1.76, 0.75, 0.74, 2.70),
    (0.86, 1.74, 0.68, 0.64, 2.55),
    (1.14, 1.72, 0.58, 0.53, 2.40),
    (1.48, 1.70, 0.47, 0.42, 2.30),
    (1.84, 1.69, 0.36, 0.33, 2.20),
    (2.18, 1.69, 0.27, 0.25, 2.10),
    (2.48, 1.70, 0.19, 0.18, 2.05),
    (2.74, 1.71, 0.12, 0.12, 2.00),
    (2.94, 1.72, 0.045, 0.055, 2.00),
]


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def make_fuselage_livery_material() -> bpy.types.Material:
    material = make_material("Warm ivory fuselage with integrated turquoise sweep", "F4E7CF", roughness=0.32, coat=0.36)
    node_tree = material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    principled = nodes.get("Principled BSDF")
    if principled is None:
        return material

    geometry = nodes.new("ShaderNodeNewGeometry")
    geometry.label = "World-space paint datum"
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Position"], separate.inputs["Vector"])

    rise = nodes.new("ShaderNodeMath")
    rise.operation = "MULTIPLY"
    rise.inputs[1].default_value = 0.040
    links.new(separate.outputs["X"], rise.inputs[0])

    center_height = nodes.new("ShaderNodeMath")
    center_height.operation = "ADD"
    center_height.inputs[1].default_value = 1.700
    links.new(rise.outputs[0], center_height.inputs[0])

    distance_from_sweep = nodes.new("ShaderNodeMath")
    distance_from_sweep.operation = "SUBTRACT"
    links.new(separate.outputs["Z"], distance_from_sweep.inputs[0])
    links.new(center_height.outputs[0], distance_from_sweep.inputs[1])
    absolute_distance = nodes.new("ShaderNodeMath")
    absolute_distance.operation = "ABSOLUTE"
    links.new(distance_from_sweep.outputs[0], absolute_distance.inputs[0])

    soft_band = nodes.new("ShaderNodeValToRGB")
    soft_band.label = "Paint edge feather"
    soft_band.color_ramp.interpolation = "EASE"
    soft_band.color_ramp.elements[0].position = 0.145
    soft_band.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    soft_band.color_ramp.elements[1].position = 0.205
    soft_band.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    links.new(absolute_distance.outputs[0], soft_band.inputs["Fac"])

    after_cowling = nodes.new("ShaderNodeMath")
    after_cowling.operation = "GREATER_THAN"
    after_cowling.inputs[1].default_value = -2.10
    links.new(separate.outputs["X"], after_cowling.inputs[0])
    before_tail = nodes.new("ShaderNodeMath")
    before_tail.operation = "LESS_THAN"
    before_tail.inputs[1].default_value = 2.10
    links.new(separate.outputs["X"], before_tail.inputs[0])

    longitudinal_mask = nodes.new("ShaderNodeMath")
    longitudinal_mask.operation = "MULTIPLY"
    links.new(after_cowling.outputs[0], longitudinal_mask.inputs[0])
    links.new(before_tail.outputs[0], longitudinal_mask.inputs[1])
    paint_mask = nodes.new("ShaderNodeMath")
    paint_mask.operation = "MULTIPLY"
    links.new(soft_band.outputs["Color"], paint_mask.inputs[0])
    links.new(longitudinal_mask.outputs[0], paint_mask.inputs[1])

    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.label = "Ivory and turquoise aircraft enamel"
    color_mix.blend_type = "MIX"
    color_mix.inputs[1].default_value = hex_color("F4E7CF")
    color_mix.inputs[2].default_value = hex_color("3FA5A3")
    links.new(paint_mask.outputs[0], color_mix.inputs[0])
    links.new(color_mix.outputs["Color"], principled.inputs["Base Color"])
    return material


def surface_materials() -> dict[str, bpy.types.Material]:
    shell = make_material("Warm ivory aircraft shell", "F4E7CF", roughness=0.32, coat=0.36)
    fuselage_shell = make_fuselage_livery_material()
    glass = make_material("Integrated teal cockpit glazing", "176E86", roughness=0.12, metallic=0.08, coat=0.78)
    coral = make_material("Coral control and tip accent", "E86F68", roughness=0.34, coat=0.34)
    return {
        "shell": shell,
        "fuselage_shell": fuselage_shell,
        "glass": glass,
        "accent": coral,
        "prop": make_material("Coral propeller enamel", "D95F5B", roughness=0.30, coat=0.42),
        "tip_yellow": make_material("Safety yellow propeller tips", "F4C95D", roughness=0.32, coat=0.34),
        "gap": make_material("Functional gaps and pupils", "20343D", roughness=0.46, coat=0.10),
        "rubber": make_material("Tire rubber", "172027", roughness=0.66, coat=0.04),
        "metal": make_material("Satin aluminum", "A8B3B8", roughness=0.26, metallic=0.74, coat=0.18),
        "dark_metal": make_material("Dark hardware", "3B474E", roughness=0.40, metallic=0.55),
        "white": make_material("Eye and lens white", "FFFDF6", roughness=0.20, coat=0.46),
        "warm_light": make_emissive_material("Warm landing light", "FFF1C7", 7.0),
        "red_light": make_emissive_material("Left navigation light", "FF4B55", 5.0),
        "green_light": make_emissive_material("Right navigation light", "4BE29B", 5.0),
        "platform": make_material("Pastel studio floor", "BBD1D8", roughness=0.58, coat=0.08),
    }


def mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    materials: list[bpy.types.Material],
    face_materials: list[int] | None = None,
    *,
    subdivision: int = 0,
    bevel: float = 0.0,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for material in materials:
        obj.data.materials.append(material)
    for index, polygon in enumerate(obj.data.polygons):
        polygon.use_smooth = True
        if face_materials is not None and index < len(face_materials):
            polygon.material_index = face_materials[index]
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    if subdivision:
        modifier = obj.modifiers.new("Continuous outer mold line", "SUBSURF")
        modifier.subdivision_type = "CATMULL_CLARK"
        modifier.levels = subdivision
        modifier.render_levels = subdivision
        modifier.show_only_control_edges = True
    return obj


def signed_power(value: float, power: float) -> float:
    return math.copysign(abs(value) ** power, value)


def angle_in_range(angle: float, low: float, high: float) -> bool:
    angle %= math.tau
    low %= math.tau
    high %= math.tau
    if low <= high:
        return low <= angle <= high
    return angle >= low or angle <= high


def circular_angle_distance(first: float, second: float) -> float:
    return abs((first - second + math.pi) % math.tau - math.pi)


def fuselage_face_material(x_mid: float, angle_mid: float) -> int:
    # The glazing is part of the same continuous grid as the fuselage shell.
    windshield_left = angle_in_range(angle_mid, math.radians(25.0), math.radians(77.0))
    windshield_right = angle_in_range(angle_mid, math.radians(103.0), math.radians(155.0))
    if -1.61 <= x_mid <= -1.14 and (windshield_left or windshield_right):
        return 1

    side_left = angle_in_range(angle_mid, math.radians(8.0), math.radians(66.0))
    side_right = angle_in_range(angle_mid, math.radians(114.0), math.radians(172.0))
    door_window = -1.01 <= x_mid <= -0.19
    rear_window = 0.13 <= x_mid <= 0.59
    if (door_window or rear_window) and (side_left or side_right):
        return 1

    return 0


def build_fuselage(mat: dict[str, bpy.types.Material]) -> bpy.types.Object:
    ring_count = 112
    vertices: list[tuple[float, float, float]] = []
    for x, center_z, radius_y, radius_z, exponent in FUSELAGE_STATIONS:
        power = 2.0 / exponent
        for index in range(ring_count):
            angle = math.tau * index / ring_count
            y = radius_y * signed_power(math.cos(angle), power)
            z = center_z + radius_z * signed_power(math.sin(angle), power)
            vertices.append((x, y, z))

    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    for section in range(len(FUSELAGE_STATIONS) - 1):
        current = section * ring_count
        following = (section + 1) * ring_count
        x_mid = (FUSELAGE_STATIONS[section][0] + FUSELAGE_STATIONS[section + 1][0]) * 0.5
        for index in range(ring_count):
            nxt = (index + 1) % ring_count
            faces.append((current + index, following + index, following + nxt, current + nxt))
            angle_mid = math.tau * (index + 0.5) / ring_count
            face_materials.append(fuselage_face_material(x_mid, angle_mid))

    faces.append(tuple(reversed(range(ring_count))))
    face_materials.append(0)
    final = (len(FUSELAGE_STATIONS) - 1) * ring_count
    faces.append(tuple(final + index for index in range(ring_count)))
    face_materials.append(0)

    obj = mesh_object(
        "V4_Continuous_Fuselage_Shell",
        vertices,
        faces,
        [mat["fuselage_shell"], mat["glass"]],
        face_materials,
        subdivision=1,
    )
    obj["construction"] = "single continuous superellipse quad shell with integrated glazing regions"
    obj["topology_rule"] = "local station density only at glazing, carry-through, gear frame, and tail attachment"
    return obj


def interpolate_fuselage_station(x: float) -> tuple[float, float, float, float]:
    if x <= FUSELAGE_STATIONS[0][0]:
        _, center_z, radius_y, radius_z, exponent = FUSELAGE_STATIONS[0]
        return center_z, radius_y, radius_z, exponent
    if x >= FUSELAGE_STATIONS[-1][0]:
        _, center_z, radius_y, radius_z, exponent = FUSELAGE_STATIONS[-1]
        return center_z, radius_y, radius_z, exponent
    for left, right in zip(FUSELAGE_STATIONS, FUSELAGE_STATIONS[1:], strict=True):
        if left[0] <= x <= right[0]:
            factor = (x - left[0]) / (right[0] - left[0])
            return tuple(left[index] + (right[index] - left[index]) * factor for index in range(1, 5))  # type: ignore[return-value]
    raise RuntimeError("fuselage station interpolation failed")


def fuselage_upper_z(x: float, y: float) -> float:
    center_z, radius_y, radius_z, exponent = interpolate_fuselage_station(x)
    normalized_y = min(0.999, abs(y) / max(radius_y, 0.001))
    remaining = max(0.0, 1.0 - normalized_y**exponent)
    return center_z + radius_z * remaining ** (1.0 / exponent)


def naca(chord_fraction: float, camber: float, camber_position: float, thickness: float) -> tuple[float, float]:
    x = max(0.000001, min(1.0, chord_fraction))
    yt = 5.0 * thickness * (
        0.2969 * math.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1036 * x**4
    )
    if camber == 0.0:
        return 0.0, yt
    if x < camber_position:
        yc = camber / camber_position**2 * (2.0 * camber_position * x - x**2)
    else:
        yc = camber / (1.0 - camber_position) ** 2 * (
            1.0 - 2.0 * camber_position + 2.0 * camber_position * x - x**2
        )
    return yc, yt


def airfoil_outline(samples: int, camber: float, camber_position: float, thickness: float) -> list[tuple[float, float]]:
    chord_values = [0.5 - 0.5 * math.cos(math.pi * index / (samples - 1)) for index in range(samples)]
    upper = []
    for chord_fraction in chord_values:
        yc, yt = naca(chord_fraction, camber, camber_position, thickness)
        upper.append((chord_fraction, yc + yt))
    lower = []
    for chord_fraction in reversed(chord_values[1:-1]):
        yc, yt = naca(chord_fraction, camber, camber_position, thickness)
        lower.append((chord_fraction, yc - yt))
    return upper + lower


def wing_planform(span: float) -> tuple[float, float, float]:
    ratio = min(1.0, abs(span) / WING_HALF_SPAN)
    leading = -1.04 + 0.30 * ratio + 0.07 * ratio**6
    chord = 1.82 - 0.66 * ratio - 0.16 * ratio**7
    center_z = 2.78 + 0.23 * ratio**1.35
    return leading, chord, center_z


def tail_planform(span: float) -> tuple[float, float, float]:
    ratio = min(1.0, abs(span) / TAIL_HALF_SPAN)
    leading = 1.68 + 0.34 * ratio
    chord = 1.30 - 0.58 * ratio - 0.08 * ratio**7
    # Mount the stabilizer on the upper tail-cone shoulder.  Keeping its neutral
    # plane just below the local crown gives the root a short, clean emergence
    # instead of a long coincident overlap with the fuselage skin.
    center_z = 1.90 + 0.035 * ratio
    return leading, chord, center_z


Planform = Callable[[float], tuple[float, float, float]]


def airfoil_coordinate(
    span: float,
    chord_fraction: float,
    upper: bool,
    planform: Planform,
    *,
    camber: float,
    camber_position: float,
    thickness: float,
) -> Vector:
    leading, chord, center_z = planform(span)
    yc, yt = naca(chord_fraction, camber, camber_position, thickness)
    return Vector((leading + chord * chord_fraction, span, center_z + chord * (yc + (yt if upper else -yt))))


def build_horizontal_airfoil(
    name: str,
    span_stations: list[float],
    planform: Planform,
    mat: dict[str, bpy.types.Material],
    *,
    camber: float,
    camber_position: float,
    thickness: float,
    tip_start: float,
    rounded_tip_ratio: float = 0.14,
) -> bpy.types.Object:
    outline = airfoil_outline(34, camber, camber_position, thickness)
    vertices: list[tuple[float, float, float]] = []
    maximum_span = max(abs(span_stations[0]), abs(span_stations[-1]))
    for span in span_stations:
        leading, chord, center_z = planform(span)
        # Elliptically collapse the outer stations around local mid-chord.  This
        # gives the planform a controlled round tip with several tangent-setting
        # rings, not a blunt cap or a single pinched polygon.
        if abs(span) > tip_start:
            tip_progress = (abs(span) - tip_start) / max(maximum_span - tip_start, 0.001)
            tip_scale = max(rounded_tip_ratio, math.sqrt(max(0.0, 1.0 - tip_progress**2)))
            original_chord = chord
            chord *= tip_scale
            leading += (original_chord - chord) * 0.5
        for chord_fraction, vertical_fraction in outline:
            vertices.append((leading + chord * chord_fraction, span, center_z + chord * vertical_fraction))

    outline_count = len(outline)
    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    for span_index in range(len(span_stations) - 1):
        span_mid = abs((span_stations[span_index] + span_stations[span_index + 1]) * 0.5)
        for outline_index in range(outline_count):
            nxt = (outline_index + 1) % outline_count
            current = span_index * outline_count
            following = (span_index + 1) * outline_count
            faces.append((current + outline_index, following + outline_index, following + nxt, current + nxt))
            face_materials.append(1 if span_mid >= tip_start else 0)
    faces.append(tuple(reversed(range(outline_count))))
    face_materials.append(1)
    final = (len(span_stations) - 1) * outline_count
    faces.append(tuple(final + index for index in range(outline_count)))
    face_materials.append(1)

    obj = mesh_object(
        name,
        vertices,
        faces,
        [mat["shell"], mat["accent"]],
        face_materials,
        bevel=0.008,
    )
    obj["surface_rule"] = "one uninterrupted parent airfoil; controls are derived regions, not independently shaped slabs"
    return obj


def build_wing(mat: dict[str, bpy.types.Material]) -> bpy.types.Object:
    span_stations = [-4.25, -4.17, -4.02, -3.82, -2.55, -0.92, -0.72, -0.48, 0.0, 0.48, 0.72, 0.92, 2.55, 3.82, 4.02, 4.17, 4.25]
    obj = build_horizontal_airfoil(
        "V4_Continuous_Parent_Wing",
        span_stations,
        wing_planform,
        mat,
        camber=0.02,
        camber_position=0.40,
        thickness=0.12,
        tip_start=3.82,
    )
    obj["root_strategy"] = "zero-dihedral center section with dihedral introduced outboard of cabin"
    obj["front_spar_fraction"] = 0.28
    obj["rear_spar_fraction"] = 0.66
    return obj


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def build_carrythrough_fairing(mat: dict[str, bpy.types.Material]) -> bpy.types.Object:
    # A restrained saddle lives almost entirely inside the roof/wing overlap.
    # Only its shoulder fillet is allowed to show, avoiding a second shelf in
    # strict side view while retaining the carry-through volume at the cabin.
    sections = [
        (-1.12, 2.62, 0.12, 0.020, 2.00),
        (-1.00, 2.66, 0.44, 0.030, 2.25),
        (-0.75, 2.68, 0.68, 0.042, 2.55),
        (-0.25, 2.69, 0.74, 0.048, 2.70),
        (0.25, 2.68, 0.68, 0.040, 2.55),
        (0.58, 2.64, 0.42, 0.028, 2.25),
        (0.75, 2.58, 0.10, 0.018, 2.00),
    ]
    ring_count = 28
    vertices: list[tuple[float, float, float]] = []
    for x, center_z, radius_y, radius_z, exponent in sections:
        power = 2.0 / exponent
        for index in range(ring_count):
            angle = math.tau * index / ring_count
            vertices.append(
                (
                    x,
                    radius_y * signed_power(math.cos(angle), power),
                    center_z + radius_z * signed_power(math.sin(angle), power),
                )
            )
    faces: list[tuple[int, ...]] = []
    for section_index in range(len(sections) - 1):
        current = section_index * ring_count
        following = (section_index + 1) * ring_count
        for index in range(ring_count):
            nxt = (index + 1) % ring_count
            faces.append((current + index, following + index, following + nxt, current + nxt))
    faces.append(tuple(reversed(range(ring_count))))
    final = (len(sections) - 1) * ring_count
    faces.append(tuple(final + index for index in range(ring_count)))
    obj = mesh_object(
        "V4_Wing_Carrythrough_Saddle_Fairing",
        vertices,
        faces,
        [mat["shell"]],
        subdivision=1,
    )
    obj["continuity"] = "purposeful longitudinal saddle loft buried into cabin roof and parent-wing root volume"
    return obj


def build_tail(mat: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, bpy.types.Object]:
    horizontal = build_horizontal_airfoil(
        "V4_Continuous_Horizontal_Tail",
        [-1.55, -1.49, -1.42, -0.46, 0.0, 0.46, 1.42, 1.49, 1.55],
        tail_planform,
        mat,
        camber=0.0,
        camber_position=0.40,
        thickness=0.10,
        tip_start=1.42,
    )

    outline = airfoil_outline(30, 0.0, 0.40, 0.11)
    z_stations = [1.64, 1.82, 2.10, 2.58, 3.02, 3.30, 3.40, 3.47, 3.50]
    vertices: list[tuple[float, float, float]] = []
    for station_index, z in enumerate(z_stations):
        ratio = (z - z_stations[0]) / (z_stations[-1] - z_stations[0])
        leading = 1.46 + 0.80 * ratio**1.18
        chord = 1.58 - 1.28 * ratio**0.82
        if z > 3.30:
            tip_progress = (z - 3.30) / 0.20
            tip_scale = max(0.18, math.sqrt(max(0.0, 1.0 - tip_progress**2)))
            original_chord = chord
            chord *= tip_scale
            leading += (original_chord - chord) * 0.5
        for chord_fraction, thickness_fraction in outline:
            vertices.append((leading + chord * chord_fraction, chord * thickness_fraction, z))

    outline_count = len(outline)
    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    for station_index in range(len(z_stations) - 1):
        for outline_index in range(outline_count):
            nxt = (outline_index + 1) % outline_count
            current = station_index * outline_count
            following = (station_index + 1) * outline_count
            faces.append((current + outline_index, current + nxt, following + nxt, following + outline_index))
            chord_mid = (outline[outline_index][0] + outline[nxt][0]) * 0.5
            face_materials.append(1 if chord_mid > 0.72 else 0)
    faces.append(tuple(reversed(range(outline_count))))
    face_materials.append(0)
    final = (len(z_stations) - 1) * outline_count
    faces.append(tuple(final + index for index in range(outline_count)))
    face_materials.append(1)
    vertical = mesh_object(
        "V4_Continuous_Vertical_Tail",
        vertices,
        faces,
        [mat["shell"], mat["accent"]],
        face_materials,
        bevel=0.010,
    )
    vertical["control_rule"] = "rudder boundary derived at 72 percent local chord"
    return horizontal, vertical


def build_dorsal_fillet(mat: dict[str, bpy.types.Material]) -> bpy.types.Object:
    x_stations = [1.10, 1.34, 1.58, 1.82, 2.06, 2.24]
    half_widths = [0.025, 0.06, 0.105, 0.13, 0.11, 0.055]
    base_heights = [1.98, 2.02, 2.08, 2.16, 2.24, 2.30]
    top_heights = [2.00, 2.08, 2.24, 2.48, 2.78, 3.02]
    vertices: list[tuple[float, float, float]] = []
    for x, half_width, base_z, top_z in zip(x_stations, half_widths, base_heights, top_heights, strict=True):
        vertices.extend(
            [
                (x, -half_width, base_z),
                (x, -half_width * 0.55, top_z),
                (x, half_width * 0.55, top_z),
                (x, half_width, base_z),
            ]
        )
    faces: list[tuple[int, ...]] = []
    for index in range(len(x_stations) - 1):
        current = index * 4
        following = (index + 1) * 4
        for edge in range(4):
            nxt = (edge + 1) % 4
            faces.append((current + edge, following + edge, following + nxt, current + nxt))
    faces.append((0, 1, 2, 3))
    final = (len(x_stations) - 1) * 4
    faces.append((final + 3, final + 2, final + 1, final))
    obj = mesh_object("V4_Dorsal_Tail_Fillet", vertices, faces, [mat["shell"]], subdivision=2)
    obj["continuity"] = "tapered dorsal load-path fairing, not a generic primitive"
    return obj


def beam(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    width: float,
    depth: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    start_vec = Vector(start)
    end_vec = Vector(end)
    direction = end_vec - start_vec
    midpoint = (start_vec + end_vec) * 0.5
    obj = add_beveled_cube(
        name,
        tuple(midpoint),
        (width, depth, direction.length),
        material,
        bevel=min(width, depth) * 0.28,
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return obj


def add_joint_empty(
    name: str,
    location: tuple[float, float, float],
    axis: tuple[float, float, float],
    role: str,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = 0.14
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector(axis).normalized().to_track_quat("Z", "Y")
    obj["role"] = role
    obj["axis_world"] = axis
    obj.hide_render = True
    bpy.context.collection.objects.link(obj)
    return obj


def create_wheel(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    side: int,
    mat: dict[str, bpy.types.Material],
) -> None:
    add_torus(
        f"{name}_Tire",
        location,
        radius * 0.72,
        radius * 0.28,
        mat["rubber"],
        rotation=(math.radians(90.0), 0.0, 0.0),
        scale=(1.0, 0.90, 1.0),
    )
    add_cylinder(
        f"{name}_Hub",
        location,
        radius * 0.38,
        radius * 0.36,
        mat["metal"],
        rotation=(math.radians(90.0), 0.0, 0.0),
        vertices=40,
    )
    add_joint_empty(
        f"JNT_{name}_AXLE",
        location,
        (0.0, float(side), 0.0),
        "wheel axle",
    )


def build_landing_gear(mat: dict[str, bpy.types.Material]) -> None:
    main_radius = 0.42
    for side, label in ((-1, "Right"), (1, "Left")):
        wheel_location = (0.16, side * 1.14, GROUND_Z + main_radius)
        attachment = (0.02, side * 0.57, 1.17)
        leg_end = (0.16, side * 1.14, 0.58)
        beam(f"{label}_Main_Spring_Gear", attachment, leg_end, 0.12, 0.17, mat["metal"])
        add_cylinder_between(
            f"{label}_Main_Axle",
            (0.16, side * 1.02, 0.42),
            (0.16, side * 1.22, 0.42),
            0.055,
            mat["dark_metal"],
        )
        create_wheel(f"{label}_Main_Wheel", wheel_location, main_radius, side, mat)
        add_joint_empty(
            f"HP_{label}_MAIN_GEAR_FRAME",
            attachment,
            (0.0, 0.0, 1.0),
            "reinforced lower cabin frame; main axle is aft of the design CG datum",
        )

    nose_radius = 0.31
    nose_location = (-2.08, 0.0, GROUND_Z + nose_radius)
    upper = (-1.98, 0.0, 1.15)
    lower = (-2.08, 0.0, 0.47)
    add_cylinder_between("Nose_Gear_Oleo", upper, lower, 0.066, mat["metal"])
    for side in (-1, 1):
        beam(
            f"Nose_Gear_Fork_{'Right' if side < 0 else 'Left'}",
            (-2.08, side * 0.075, 0.50),
            (-2.08, side * 0.145, 0.31),
            0.060,
            0.045,
            mat["dark_metal"],
        )
    create_wheel("Nose_Wheel", nose_location, nose_radius, -1, mat)
    add_joint_empty("JNT_NOSE_STEERING", lower, (0.0, 0.0, 1.0), "steerable nose-gear axis")
    add_joint_empty(
        "HP_NOSE_GEAR_FIREWALL",
        upper,
        (0.0, 0.0, 1.0),
        "nose-gear load enters the forward fuselage/firewall region",
    )


def build_lift_struts(mat: dict[str, bpy.types.Material]) -> None:
    for side, label in ((-1, "Right"), (1, "Left")):
        lower = (-0.02, side * 0.72, 1.45)
        span = side * 2.50
        leading, chord, _ = wing_planform(span)
        chord_fraction = 0.30
        upper_vector = airfoil_coordinate(
            span,
            chord_fraction,
            False,
            wing_planform,
            camber=0.02,
            camber_position=0.40,
            thickness=0.12,
        )
        upper = (upper_vector.x, upper_vector.y, upper_vector.z - 0.035)
        beam(f"{label}_Lift_Strut", lower, upper, 0.105, 0.145, mat["shell"])
        add_cylinder_between(
            f"{label}_Lower_Strut_Fitting",
            (lower[0] - 0.05, lower[1], lower[2]),
            (lower[0] + 0.05, lower[1], lower[2]),
            0.070,
            mat["metal"],
        )
        add_cylinder_between(
            f"{label}_Upper_Strut_Fitting",
            (upper[0] - 0.055, upper[1], upper[2]),
            (upper[0] + 0.055, upper[1], upper[2]),
            0.065,
            mat["metal"],
        )
        add_joint_empty(
            f"HP_{label}_STRUT_UPPER_FRONT_SPAR",
            upper,
            (0.0, float(side), 0.0),
            "upper lift-strut fitting derived from the 30-percent-chord front-spar datum",
        )
        add_joint_empty(
            f"HP_{label}_STRUT_LOWER_FRAME",
            lower,
            (0.0, 0.0, 1.0),
            "lower lift-strut fitting on reinforced cabin frame",
        )


def propeller_blade(
    name: str,
    angle: float,
    material: bpy.types.Material,
    tip_material: bpy.types.Material,
) -> bpy.types.Object:
    center = Vector((-3.075, 0.0, 1.70))
    radial = Vector((0.0, math.cos(angle), math.sin(angle)))
    tangent = Vector((0.0, -math.sin(angle), math.cos(angle)))
    samples = [0.18, 0.36, 0.62, 0.91, 1.18]
    widths = [0.055, 0.080, 0.105, 0.080, 0.032]
    sweep = [0.00, 0.012, 0.030, 0.052, 0.075]
    half_depth = 0.026
    vertices: list[tuple[float, float, float]] = []
    for depth_sign in (-1.0, 1.0):
        for radial_distance, width, tangential_shift in zip(samples, widths, sweep, strict=True):
            point = center + radial * radial_distance + tangent * tangential_shift
            vertices.append(tuple(point - tangent * width + Vector((depth_sign * half_depth, 0.0, 0.0))))
            vertices.append(tuple(point + tangent * width + Vector((depth_sign * half_depth, 0.0, 0.0))))
    count = len(samples) * 2
    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    for index in range(len(samples) - 1):
        a = index * 2
        b = a + 2
        faces.append((a, b, b + 1, a + 1))
        faces.append((a + count + 1, b + count + 1, b + count, a + count))
        face_materials.extend([1 if index == len(samples) - 2 else 0] * 2)
    for index in range(len(samples) - 1):
        left = index * 2
        next_left = (index + 1) * 2
        right = left + 1
        next_right = next_left + 1
        faces.append((left, left + count, next_left + count, next_left))
        faces.append((right, next_right, next_right + count, right + count))
        face_materials.extend([1 if index == len(samples) - 2 else 0] * 2)
    faces.append((0, 1, 1 + count, count))
    face_materials.append(0)
    tip_left = (len(samples) - 1) * 2
    tip_right = tip_left + 1
    faces.append((tip_left, tip_left + count, tip_right + count, tip_right))
    face_materials.append(1)
    obj = mesh_object(name, vertices, faces, [material, tip_material], face_materials, bevel=0.025)
    return obj


def build_propeller(mat: dict[str, bpy.types.Material]) -> None:
    clocking = math.radians(32.0)
    propeller_blade("Propeller_Blade_A", clocking, mat["prop"], mat["tip_yellow"])
    propeller_blade("Propeller_Blade_B", clocking + math.pi, mat["prop"], mat["tip_yellow"])
    add_cylinder(
        "Propeller_Hub",
        (-3.03, 0.0, 1.70),
        0.18,
        0.20,
        mat["metal"],
        rotation=(0.0, math.radians(90.0), 0.0),
        vertices=48,
    )
    spinner = add_uv_sphere("Propeller_Spinner", (-3.16, 0.0, 1.70), (0.25, 0.25, 0.25), mat["accent"], segments=40)
    spinner.scale.x = 1.20
    add_joint_empty("JNT_PROPELLER_AXIS", (-3.03, 0.0, 1.70), (1.0, 0.0, 0.0), "engine crankshaft and propeller axis")


def build_surface_proof_details(mat: dict[str, bpy.types.Material]) -> None:
    # Functional openings remain separate negative-color inserts because they are
    # real air inlets, not painted panel lines.
    for y in (-0.24, 0.24):
        intake = add_beveled_cube(
            f"Cowling_Lower_Intake_{'Right' if y < 0 else 'Left'}",
            (-2.73, y, 1.47),
            (0.045, 0.28, 0.12),
            mat["gap"],
            bevel=0.045,
        )
        intake.rotation_euler.y = math.radians(2.0)

    for side, label in ((-1, "Right"), (1, "Left")):
        leading, chord, center_z = wing_planform(side * WING_HALF_SPAN)
        light_material = mat["green_light"] if side < 0 else mat["red_light"]
        add_uv_sphere(
            f"{label}_Navigation_Light",
            (leading + chord * 0.62, side * (WING_HALF_SPAN + 0.025), center_z),
            (0.070, 0.055, 0.050),
            light_material,
            segments=28,
        )


def fuselage_surface_raw(x: float, angle: float) -> Vector:
    center_z, radius_y, radius_z, exponent = interpolate_fuselage_station(x)
    power = 2.0 / exponent
    return Vector(
        (
            x,
            radius_y * signed_power(math.cos(angle), power),
            center_z + radius_z * signed_power(math.sin(angle), power),
        )
    )


def fuselage_surface_frame(x: float, angle: float) -> tuple[Vector, Vector]:
    point = fuselage_surface_raw(x, angle)
    epsilon_x = 0.008
    epsilon_angle = math.radians(0.5)
    tangent_x = fuselage_surface_raw(x + epsilon_x, angle) - fuselage_surface_raw(x - epsilon_x, angle)
    tangent_angle = fuselage_surface_raw(x, angle + epsilon_angle) - fuselage_surface_raw(x, angle - epsilon_angle)
    normal = tangent_x.cross(tangent_angle).normalized()
    center_z, _, _, _ = interpolate_fuselage_station(x)
    radial_hint = Vector((0.0, point.y, point.z - center_z))
    if normal.dot(radial_hint) < 0.0:
        normal.negate()
    return point, normal


def fuselage_surface_coordinate(x: float, angle: float, offset: float = 0.0) -> Vector:
    point, normal = fuselage_surface_frame(x, angle)
    return point + normal * offset


def add_closed_curve(
    name: str,
    points: list[tuple[float, float, float]],
    material: bpy.types.Material,
    *,
    bevel_depth: float,
) -> bpy.types.Object:
    obj = add_curve(name, points, material, bevel_depth=bevel_depth)
    obj.data.splines[0].use_cyclic_u = True
    return obj


def add_window_frame(
    name: str,
    front_x: float,
    rear_x: float,
    lower_angle: float,
    upper_angle: float,
    material: bpy.types.Material,
) -> None:
    x_values = [front_x + (rear_x - front_x) * index / 6.0 for index in range(7)]
    angle_values = [lower_angle + (upper_angle - lower_angle) * index / 6.0 for index in range(7)]
    add_curve(
        f"{name}_Lower_Frame",
        [tuple(fuselage_surface_coordinate(x, lower_angle, 0.012)) for x in x_values],
        material,
        bevel_depth=0.016,
    )
    add_curve(
        f"{name}_Upper_Frame",
        [tuple(fuselage_surface_coordinate(x, upper_angle, 0.012)) for x in x_values],
        material,
        bevel_depth=0.016,
    )
    add_curve(
        f"{name}_Front_Frame",
        [tuple(fuselage_surface_coordinate(front_x, angle, 0.012)) for angle in angle_values],
        material,
        bevel_depth=0.016,
    )
    add_curve(
        f"{name}_Rear_Frame",
        [tuple(fuselage_surface_coordinate(rear_x, angle, 0.012)) for angle in angle_values],
        material,
        bevel_depth=0.016,
    )


def add_flat_disc(
    name: str,
    point: Vector,
    normal: Vector,
    width: float,
    height: float,
    depth: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    obj = add_uv_sphere(name, tuple(point), (width, height, depth), material, segments=40)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = normal.normalized().to_track_quat("Z", "Y")
    return obj


def build_window_frames_and_face(mat: dict[str, bpy.types.Material]) -> None:
    # The frame curves cover the material boundary and visually round each inset
    # glazing corner without adding a second glass plate.
    for side, label in ((1, "Left"), (-1, "Right")):
        if side > 0:
            windscreen_angles = (math.radians(25.0), math.radians(77.0))
            side_angles = (math.radians(8.0), math.radians(66.0))
        else:
            windscreen_angles = (math.radians(155.0), math.radians(103.0))
            side_angles = (math.radians(172.0), math.radians(114.0))
        add_window_frame(
            f"{label}_Windscreen",
            -1.62,
            -1.13,
            windscreen_angles[0],
            windscreen_angles[1],
            mat["shell"],
        )
        add_window_frame(
            f"{label}_Door_Window",
            -1.02,
            -0.18,
            side_angles[0],
            side_angles[1],
            mat["shell"],
        )
        add_window_frame(
            f"{label}_Rear_Window",
            0.14,
            0.58,
            side_angles[0],
            side_angles[1],
            mat["shell"],
        )

        # One eye per windscreen half makes the expression read from both the
        # front and three-quarter views while leaving the side windows functional.
        eye_angle = math.radians(52.0 if side > 0 else 128.0)
        _, normal = fuselage_surface_frame(-1.50, eye_angle)
        eye_point = fuselage_surface_coordinate(-1.50, eye_angle, 0.035)
        add_flat_disc(
            f"{label}_Eye_White",
            eye_point,
            normal,
            0.125,
            0.165,
            0.026,
            mat["white"],
        )
        pupil_point = eye_point + normal * 0.035 + Vector((-0.010, 0.0, -0.010))
        add_flat_disc(
            f"{label}_Eye_Pupil",
            pupil_point,
            normal,
            0.057,
            0.078,
            0.020,
            mat["gap"],
        )
        highlight_point = pupil_point + normal * 0.026 + Vector((-0.012, side * 0.012, 0.025))
        add_flat_disc(
            f"{label}_Eye_Highlight",
            highlight_point,
            normal,
            0.018,
            0.024,
            0.010,
            mat["white"],
        )

    add_curve(
        "Friendly_Cowling_Smile",
        [(-2.80, -0.24, 1.37), (-2.83, 0.0, 1.29), (-2.80, 0.24, 1.37)],
        mat["gap"],
        bevel_depth=0.018,
    )


def build_cabin_hardware(mat: dict[str, bpy.types.Material]) -> None:
    for side, label in ((1, "Left"), (-1, "Right")):
        upper_angle = math.radians(7.0 if side > 0 else 173.0)
        lower_angle = math.radians(-44.0 if side > 0 else 224.0)
        front_x = -1.05
        rear_x = 0.12
        angle_values = [upper_angle + (lower_angle - upper_angle) * index / 7.0 for index in range(8)]
        x_values = [front_x + (rear_x - front_x) * index / 8.0 for index in range(9)]
        add_curve(
            f"{label}_Cabin_Door_Forward_Seam",
            [tuple(fuselage_surface_coordinate(front_x, angle, 0.010)) for angle in angle_values],
            mat["gap"],
            bevel_depth=0.007,
        )
        add_curve(
            f"{label}_Cabin_Door_Aft_Seam",
            [tuple(fuselage_surface_coordinate(rear_x, angle, 0.010)) for angle in angle_values],
            mat["gap"],
            bevel_depth=0.007,
        )
        add_curve(
            f"{label}_Cabin_Door_Lower_Seam",
            [tuple(fuselage_surface_coordinate(x, lower_angle, 0.010)) for x in x_values],
            mat["gap"],
            bevel_depth=0.007,
        )
        handle_angle = math.radians(-2.0 if side > 0 else 182.0)
        handle_point = fuselage_surface_coordinate(-0.02, handle_angle, 0.032)
        add_beveled_cube(
            f"{label}_Cabin_Door_Handle",
            tuple(handle_point),
            (0.16, 0.040, 0.035),
            mat["dark_metal"],
            bevel=0.016,
        )

        step_y = side * 0.98
        add_cylinder_between(
            f"{label}_Cabin_Step_Stalk",
            (-0.48, side * 0.78, 1.02),
            (-0.48, step_y, 1.02),
            0.024,
            mat["metal"],
        )
        add_beveled_cube(
            f"{label}_Cabin_Step_Pad",
            (-0.48, side * 1.02, 1.02),
            (0.20, 0.10, 0.035),
            mat["dark_metal"],
            bevel=0.014,
        )


def horizontal_surface_point(
    span: float,
    chord_fraction: float,
    planform: Planform,
    *,
    camber: float,
    camber_position: float,
    thickness: float,
    upper: bool = True,
    offset: float = 0.010,
) -> Vector:
    point = airfoil_coordinate(
        span,
        chord_fraction,
        upper,
        planform,
        camber=camber,
        camber_position=camber_position,
        thickness=thickness,
    )
    point.z += offset if upper else -offset
    return point


def add_horizontal_control_layout(
    prefix: str,
    side: int,
    start_span: float,
    end_span: float,
    hinge_fraction: float,
    planform: Planform,
    material: bpy.types.Material,
    *,
    camber: float,
    thickness: float,
) -> None:
    spans = [side * (start_span + (end_span - start_span) * index / 8.0) for index in range(9)]
    hinge_points = [
        tuple(
            horizontal_surface_point(
                span,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=0.40,
                thickness=thickness,
            )
        )
        for span in spans
    ]
    add_curve(f"{prefix}_Hinge_Seam", hinge_points, material, bevel_depth=0.007)
    for boundary_name, span in (("Inboard", side * start_span), ("Outboard", side * end_span)):
        fractions = [hinge_fraction + (0.995 - hinge_fraction) * index / 6.0 for index in range(7)]
        add_curve(
            f"{prefix}_{boundary_name}_End_Seam",
            [
                tuple(
                    horizontal_surface_point(
                        span,
                        chord_fraction,
                        planform,
                        camber=camber,
                        camber_position=0.40,
                        thickness=thickness,
                    )
                )
                for chord_fraction in fractions
            ],
            material,
            bevel_depth=0.007,
        )


def vertical_tail_planform(z: float) -> tuple[float, float]:
    ratio = max(0.0, min(1.0, (z - 1.64) / (3.50 - 1.64)))
    return 1.46 + 0.80 * ratio**1.18, 1.58 - 1.28 * ratio**0.82


def vertical_tail_surface_point(z: float, chord_fraction: float, side: int, offset: float = 0.008) -> Vector:
    leading, chord = vertical_tail_planform(z)
    _, half_thickness = naca(chord_fraction, 0.0, 0.40, 0.11)
    return Vector((leading + chord * chord_fraction, side * (chord * half_thickness + offset), z))


def build_control_surface_details(mat: dict[str, bpy.types.Material]) -> None:
    for side, label in ((-1, "Right"), (1, "Left")):
        add_horizontal_control_layout(
            f"{label}_Wing_Flap",
            side,
            0.78,
            2.36,
            0.72,
            wing_planform,
            mat["gap"],
            camber=0.02,
            thickness=0.12,
        )
        add_horizontal_control_layout(
            f"{label}_Wing_Aileron",
            side,
            2.50,
            3.78,
            0.70,
            wing_planform,
            mat["gap"],
            camber=0.02,
            thickness=0.12,
        )
        add_horizontal_control_layout(
            f"{label}_Elevator",
            side,
            0.38,
            1.40,
            0.68,
            tail_planform,
            mat["gap"],
            camber=0.0,
            thickness=0.10,
        )

        flap_axis = horizontal_surface_point(
            side * 1.57,
            0.72,
            wing_planform,
            camber=0.02,
            camber_position=0.40,
            thickness=0.12,
        )
        add_joint_empty(
            f"JNT_{label.upper()}_FLAP_HINGE",
            tuple(flap_axis),
            (0.0, float(side), 0.0),
            "flap hinge axis derived from the continuous parent wing",
        )
        aileron_axis = horizontal_surface_point(
            side * 3.14,
            0.70,
            wing_planform,
            camber=0.02,
            camber_position=0.40,
            thickness=0.12,
        )
        add_joint_empty(
            f"JNT_{label.upper()}_AILERON_HINGE",
            tuple(aileron_axis),
            (0.0, float(side), 0.0),
            "aileron hinge axis derived from the continuous parent wing",
        )
        elevator_axis = horizontal_surface_point(
            side * 0.88,
            0.68,
            tail_planform,
            camber=0.0,
            camber_position=0.40,
            thickness=0.10,
        )
        add_joint_empty(
            f"JNT_{label.upper()}_ELEVATOR_HINGE",
            tuple(elevator_axis),
            (0.0, float(side), 0.0),
            "elevator hinge axis derived from the continuous stabilizer",
        )

    for side, label in ((-1, "Right"), (1, "Left")):
        z_values = [1.94 + (3.30 - 1.94) * index / 10.0 for index in range(11)]
        add_curve(
            f"{label}_Rudder_Hinge_Seam",
            [tuple(vertical_tail_surface_point(z, 0.72, side)) for z in z_values],
            mat["gap"],
            bevel_depth=0.007,
        )
        for boundary_name, z in (("Lower", 1.94), ("Upper", 3.30)):
            fractions = [0.72 + (0.985 - 0.72) * index / 6.0 for index in range(7)]
            add_curve(
                f"{label}_Rudder_{boundary_name}_End_Seam",
                [tuple(vertical_tail_surface_point(z, fraction, side)) for fraction in fractions],
                mat["gap"],
                bevel_depth=0.007,
            )
    rudder_leading, rudder_chord = vertical_tail_planform(2.55)
    add_joint_empty(
        "JNT_RUDDER_HINGE",
        (rudder_leading + rudder_chord * 0.72, 0.0, 2.55),
        (0.0, 0.0, 1.0),
        "rudder hinge axis derived from the continuous fin",
    )


def build_aircraft_service_details(mat: dict[str, bpy.types.Material]) -> None:
    # Engine-cowling break line follows a true fuselage station.
    cowling_ring = [
        tuple(fuselage_surface_coordinate(-2.10, math.tau * index / 40.0, 0.010))
        for index in range(40)
    ]
    add_closed_curve("Cowling_Access_Seam", cowling_ring, mat["gap"], bevel_depth=0.007)

    # Fuel caps sit on the upper skin near the root tanks.
    for side, label in ((-1, "Right"), (1, "Left")):
        cap_point = horizontal_surface_point(
            side * 1.33,
            0.31,
            wing_planform,
            camber=0.02,
            camber_position=0.40,
            thickness=0.12,
            offset=0.014,
        )
        add_cylinder(
            f"{label}_Wing_Fuel_Cap",
            tuple(cap_point),
            0.062,
            0.018,
            mat["metal"],
            vertices=40,
        )

    # Pitot probe on the left wing and a leading-edge landing lamp.
    pitot_mount = horizontal_surface_point(
        2.72,
        0.18,
        wing_planform,
        camber=0.02,
        camber_position=0.40,
        thickness=0.12,
        upper=False,
        offset=0.018,
    )
    add_cylinder_between(
        "Left_Wing_Pitot_Probe",
        tuple(pitot_mount),
        tuple(pitot_mount + Vector((-0.40, 0.0, -0.055))),
        0.017,
        mat["metal"],
    )
    lamp_span = 2.92
    lamp_leading, _, lamp_z = wing_planform(lamp_span)
    add_uv_sphere(
        "Left_Wing_Landing_Light",
        (lamp_leading - 0.018, lamp_span, lamp_z - 0.005),
        (0.045, 0.105, 0.060),
        mat["warm_light"],
        segments=32,
    )

    # Dorsal communications aerial, tail beacon, and a short exhaust outlet.
    aerial_base_z = fuselage_upper_z(0.90, 0.0) + 0.015
    add_cylinder_between(
        "Dorsal_Radio_Aerial",
        (0.90, 0.0, aerial_base_z),
        (1.00, 0.0, aerial_base_z + 0.31),
        0.017,
        mat["dark_metal"],
    )
    add_uv_sphere(
        "Vertical_Tail_Beacon",
        (2.39, 0.0, 3.53),
        (0.050, 0.045, 0.040),
        mat["red_light"],
        segments=28,
    )
    add_cylinder_between(
        "Engine_Exhaust_Outlet",
        (-2.10, -0.34, 1.19),
        (-1.91, -0.41, 1.05),
        0.038,
        mat["dark_metal"],
    )

    # Colored outboard hub caps add hierarchy without hiding the wheel/axle logic.
    add_cylinder(
        "Right_Main_Hubcap_Accent",
        (0.16, -1.31, 0.42),
        0.145,
        0.035,
        mat["accent"],
        rotation=(math.radians(90.0), 0.0, 0.0),
        vertices=40,
    )
    add_cylinder(
        "Left_Main_Hubcap_Accent",
        (0.16, 1.31, 0.42),
        0.145,
        0.035,
        mat["accent"],
        rotation=(math.radians(90.0), 0.0, 0.0),
        vertices=40,
    )


def build_final_details(mat: dict[str, bpy.types.Material]) -> None:
    build_window_frames_and_face(mat)
    build_cabin_hardware(mat)
    build_control_surface_details(mat)
    build_aircraft_service_details(mat)


def build_platform(mat: dict[str, bpy.types.Material]) -> None:
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=6.2, depth=0.18, location=(0.0, 0.0, -0.10))
    platform = bpy.context.object
    platform.name = "Final_Presentation_Platform"
    assign_material(platform, mat["platform"])
    bevel = platform.modifiers.new("Platform rim", "BEVEL")
    bevel.width = 0.10
    bevel.segments = 5
    smooth(platform)


def setup_scene() -> bpy.types.Object:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 128
        if hasattr(eevee, "taa_samples"):
            eevee.taa_samples = 128
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.05

    world = scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = hex_color("9FB4C0")
        background.inputs["Strength"].default_value = 0.55

    bpy.ops.object.light_add(type="AREA", location=(-4.5, -5.5, 8.0))
    key = bpy.context.object
    key.name = "Key_Softbox"
    key.data.energy = 1250.0
    key.data.shape = "DISK"
    key.data.size = 5.0
    point_at(key, (0.0, 0.0, 1.7))

    bpy.ops.object.light_add(type="AREA", location=(4.0, -2.0, 5.0))
    fill = bpy.context.object
    fill.name = "Fill_Softbox"
    fill.data.energy = 850.0
    fill.data.size = 4.0
    point_at(fill, (0.0, 0.0, 1.6))

    bpy.ops.object.light_add(type="AREA", location=(1.5, 5.5, 6.0))
    rim = bpy.context.object
    rim.name = "Rim_Softbox"
    rim.data.energy = 1100.0
    rim.data.size = 3.5
    point_at(rim, (0.5, 0.0, 2.0))

    bpy.ops.object.camera_add(location=(-7.4, -8.6, 5.3))
    camera = bpy.context.object
    camera.name = "V4_Review_Camera"
    camera.data.lens = 56.0
    camera.data.sensor_width = 36.0
    scene.camera = camera
    return camera


def render_view(
    camera: bpy.types.Object,
    path: Path,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    *,
    orthographic_scale: float | None = None,
    resolution: tuple[int, int] = (1200, 900),
) -> None:
    scene = bpy.context.scene
    camera.location = location
    point_at(camera, target)
    if orthographic_scale is None:
        camera.data.type = "PERSP"
        camera.data.lens = 56.0
    else:
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = orthographic_scale
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def create_cartoon_trainer_v4() -> None:
    clear_scene()
    mat = surface_materials()

    root = bpy.data.objects.new("V4_AIRCRAFT_MASTER", None)
    root.empty_display_type = "CIRCLE"
    root.empty_display_size = 0.35
    root["archetype"] = "Cessna-Skyhawk-inspired high-wing, strut-braced, tricycle trainer"
    root["design_method"] = "outer mold line first; derived controls and constrained hardpoints"
    root["coordinate_system"] = "X aft, Y span-left, Z up"
    root["final_stage"] = "aviation-grounded service detail and restrained character treatment"
    bpy.context.collection.objects.link(root)

    primary_objects = [
        build_fuselage(mat),
        build_wing(mat),
        build_carrythrough_fairing(mat),
        *build_tail(mat),
        build_dorsal_fillet(mat),
    ]
    for obj in primary_objects:
        obj.parent = root

    build_lift_struts(mat)
    build_landing_gear(mat)
    build_propeller(mat)
    build_surface_proof_details(mat)
    build_final_details(mat)
    build_platform(mat)

    add_joint_empty("DATUM_DESIGN_CG", (-0.43, 0.0, 1.70), (0.0, 0.0, 1.0), "design CG datum for gear and control-layout review")
    add_joint_empty("DATUM_WING_QUARTER_CHORD", (-0.585, 0.0, 2.78), (0.0, 1.0, 0.0), "root wing quarter-chord datum")

    # Every aircraft object belongs to one assembly root; presentation and
    # lighting remain outside it.  The root is identity-transformed, so parenting
    # preserves all world-space hardpoints exactly.
    for obj in list(bpy.context.scene.objects):
        if obj is root or obj.name == "Final_Presentation_Platform":
            continue
        if obj.parent is None:
            obj.parent = root

    camera = setup_scene()
    bpy.context.scene["review_gate"] = "final: four-view silhouette, surface continuity, accurate hardpoints, and derived control layout"
    bpy.context.scene["detail_policy"] = "major functional seams only; no random greebles or floating livery geometry"

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    render_view(camera, HERO_PATH, (-9.0, -10.8, 6.2), (-0.05, 0.0, 1.72), resolution=(1600, 1200))
    render_view(camera, SIDE_PATH, (0.0, -12.0, 1.72), (0.0, 0.0, 1.72), orthographic_scale=7.8, resolution=(1200, 800))
    render_view(camera, FRONT_PATH, (-12.0, 0.0, 2.30), (-0.10, 0.0, 1.80), orthographic_scale=9.4, resolution=(1000, 1000))
    render_view(camera, TOP_PATH, (0.0, 0.0, 13.0), (0.0, 0.0, 1.50), orthographic_scale=10.2, resolution=(1000, 1000))
    render_view(camera, DETAIL_PATH, (-6.8, -7.0, 4.2), (-1.05, -0.05, 1.85), resolution=(1400, 1050))

    print(
        "V4 final aircraft complete "
        f"blend={BLEND_PATH} hero={HERO_PATH} side={SIDE_PATH} front={FRONT_PATH} top={TOP_PATH} detail={DETAIL_PATH}"
    )


if __name__ == "__main__":
    create_cartoon_trainer_v4()

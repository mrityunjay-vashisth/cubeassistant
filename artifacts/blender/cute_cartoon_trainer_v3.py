from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Callable

import bpy
from mathutils import Quaternion, Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cute_airplane import (  # noqa: E402
    add_beveled_cube,
    add_cloud,
    add_curve,
    add_cylinder,
    add_cylinder_between,
    add_extruded_xz_shape,
    add_uv_sphere,
    assign_material,
    hex_color,
    make_material,
    point_at,
    smooth,
)
from cute_airplane_detailed import (  # noqa: E402
    Component,
    add_local_yz_prism,
    add_torus,
    make_emissive_material,
    make_glass_material,
    parent_keep_world,
)


BLEND_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v3.blend"
RENDER_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v3.png"
GROUND_Z = 0.0
PROP_Z = 1.82
WING_HALF_SPAN = 4.20
WING_HINGE = 0.735
TAIL_HALF_SPAN = 1.52
TAIL_HINGE = 0.69


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


def mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    material: bpy.types.Material,
    *,
    bevel: float = 0.0,
    subdivision: int = 0,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)
    smooth(obj)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    if subdivision:
        modifier = obj.modifiers.new("Loft smoothing", "SUBSURF")
        modifier.subdivision_type = "CATMULL_CLARK"
        modifier.levels = subdivision
        modifier.render_levels = subdivision
    return obj


def polyline(
    name: str,
    points: list[tuple[float, float, float]],
    material: bpy.types.Material,
    *,
    bevel: float,
    cyclic: bool = False,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{name}_Curve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for target, coordinate in zip(spline.points, points, strict=True):
        target.co = (*coordinate, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)
    return obj


def beam(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    width: float,
    depth: float,
    material: bpy.types.Material,
    *,
    bevel: float = 0.035,
) -> bpy.types.Object:
    a = Vector(start)
    b = Vector(end)
    direction = b - a
    obj = add_beveled_cube(
        name,
        tuple((a + b) * 0.5),
        (width, depth, direction.length),
        material,
        bevel=bevel,
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return obj


def hardpoint(
    component: Component,
    name: str,
    location: tuple[float, float, float],
    role: str,
    load_path: str,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "CIRCLE"
    obj.empty_display_size = 0.11
    obj.location = location
    obj["role"] = role
    obj["load_path"] = load_path
    obj["coordinates"] = "X aft, Y span, Z up"
    obj.hide_render = True
    component.collection.objects.link(obj)
    obj.parent = component.root
    return obj


def signed_power(value: float, power: float) -> float:
    return math.copysign(abs(value) ** power, value)


def loft_fuselage(
    sections: list[tuple[float, float, float, float, float]],
    material: bpy.types.Material,
) -> bpy.types.Object:
    ring_count = 48
    vertices: list[tuple[float, float, float]] = []
    for x, center_z, radius_y, radius_z, exponent in sections:
        power = 2.0 / exponent
        for index in range(ring_count):
            angle = math.tau * index / ring_count
            y = radius_y * signed_power(math.cos(angle), power)
            z = center_z + radius_z * signed_power(math.sin(angle), power)
            vertices.append((x, y, z))

    faces: list[tuple[int, ...]] = []
    for section in range(len(sections) - 1):
        current = section * ring_count
        following = (section + 1) * ring_count
        for index in range(ring_count):
            nxt = (index + 1) % ring_count
            faces.append((current + index, following + index, following + nxt, current + nxt))
    faces.append(tuple(reversed(range(ring_count))))
    final = (len(sections) - 1) * ring_count
    faces.append(tuple(final + index for index in range(ring_count)))

    obj = mesh_object(
        "Fuselage_SemiMonocoque_Loft",
        vertices,
        faces,
        material,
        subdivision=2,
    )
    obj["construction"] = "outer loft shaped by fuselage frame stations and longitudinal stringers"
    obj["frame_station_count"] = len(sections)
    return obj


def profile_ring(
    name: str,
    x: float,
    center_z: float,
    radius_y: float,
    radius_z: float,
    exponent: float,
    material: bpy.types.Material,
    thickness: float,
) -> bpy.types.Object:
    points: list[tuple[float, float, float]] = []
    power = 2.0 / exponent
    for index in range(44):
        angle = math.tau * index / 44.0
        points.append(
            (
                x,
                radius_y * signed_power(math.cos(angle), power),
                center_z + radius_z * signed_power(math.sin(angle), power),
            )
        )
    return polyline(name, points, material, bevel=thickness, cyclic=True)


def naca(chord_fraction: float, camber: float, camber_position: float, thickness: float) -> tuple[float, float]:
    x = max(0.00001, min(1.0, chord_fraction))
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


Planform = Callable[[float], tuple[float, float, float]]


def wing_planform(span: float) -> tuple[float, float, float]:
    ratio = span / WING_HALF_SPAN
    return -1.02 + 0.20 * ratio, 1.78 - 0.56 * ratio, 2.73 + 0.25 * ratio


def tail_planform(span: float) -> tuple[float, float, float]:
    ratio = span / TAIL_HALF_SPAN
    return 1.70 + 0.25 * ratio, 1.28 - 0.36 * ratio, 2.01 + 0.035 * ratio


def airfoil_point(
    span: float,
    side: int,
    chord_fraction: float,
    planform: Planform,
    *,
    camber: float,
    camber_position: float,
    thickness: float,
    upper: bool,
) -> Vector:
    leading, chord, center_z = planform(span)
    yc, yt = naca(chord_fraction, camber, camber_position, thickness)
    return Vector(
        (
            leading + chord_fraction * chord,
            side * span,
            center_z + chord * (yc + (yt if upper else -yt)),
        )
    )


def airfoil_segment(
    name: str,
    span_start: float,
    span_end: float,
    side: int,
    chord_start: float,
    chord_end: float,
    material: bpy.types.Material,
    planform: Planform,
    *,
    camber: float,
    camber_position: float,
    thickness: float,
    hinge_fraction: float | None = None,
    deflection: float = 0.0,
) -> bpy.types.Object:
    span_samples = 6
    chord_samples = 15
    span_values = [
        span_start + (span_end - span_start) * index / (span_samples - 1)
        for index in range(span_samples)
    ]
    chord_values = []
    for index in range(chord_samples):
        phase = index / (chord_samples - 1)
        eased = 0.5 - 0.5 * math.cos(math.pi * phase)
        chord_values.append(chord_start + (chord_end - chord_start) * eased)

    origin = None
    rotation = None
    if hinge_fraction is not None and deflection:
        inner = (
            airfoil_point(
                span_start,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=True,
            )
            + airfoil_point(
                span_start,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=False,
            )
        ) * 0.5
        outer = (
            airfoil_point(
                span_end,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=True,
            )
            + airfoil_point(
                span_end,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=False,
            )
        ) * 0.5
        origin = inner
        rotation = Quaternion((outer - inner).normalized(), math.radians(deflection * side))

    vertices: list[tuple[float, float, float]] = []
    for upper in (True, False):
        for span in span_values:
            for chord_fraction in chord_values:
                coordinate = airfoil_point(
                    span,
                    side,
                    chord_fraction,
                    planform,
                    camber=camber,
                    camber_position=camber_position,
                    thickness=thickness,
                    upper=upper,
                )
                if origin is not None and rotation is not None:
                    coordinate = origin + rotation @ (coordinate - origin)
                vertices.append(tuple(coordinate))

    surface_size = span_samples * chord_samples

    def vertex(upper: bool, span_index: int, chord_index: int) -> int:
        return (0 if upper else surface_size) + span_index * chord_samples + chord_index

    faces: list[tuple[int, ...]] = []
    for span_index in range(span_samples - 1):
        for chord_index in range(chord_samples - 1):
            faces.append(
                (
                    vertex(True, span_index, chord_index),
                    vertex(True, span_index + 1, chord_index),
                    vertex(True, span_index + 1, chord_index + 1),
                    vertex(True, span_index, chord_index + 1),
                )
            )
            faces.append(
                (
                    vertex(False, span_index, chord_index + 1),
                    vertex(False, span_index + 1, chord_index + 1),
                    vertex(False, span_index + 1, chord_index),
                    vertex(False, span_index, chord_index),
                )
            )
        final_chord = chord_samples - 1
        faces.append(
            (
                vertex(True, span_index, 0),
                vertex(False, span_index, 0),
                vertex(False, span_index + 1, 0),
                vertex(True, span_index + 1, 0),
            )
        )
        faces.append(
            (
                vertex(True, span_index, final_chord),
                vertex(True, span_index + 1, final_chord),
                vertex(False, span_index + 1, final_chord),
                vertex(False, span_index, final_chord),
            )
        )
    for chord_index in range(chord_samples - 1):
        faces.append(
            (
                vertex(True, 0, chord_index + 1),
                vertex(True, 0, chord_index),
                vertex(False, 0, chord_index),
                vertex(False, 0, chord_index + 1),
            )
        )
        end = span_samples - 1
        faces.append(
            (
                vertex(True, end, chord_index),
                vertex(True, end, chord_index + 1),
                vertex(False, end, chord_index + 1),
                vertex(False, end, chord_index),
            )
        )

    obj = mesh_object(name, vertices, faces, material, bevel=0.010)
    obj["airfoil"] = f"NACA-like {int(camber*100)}{int(camber_position*10)}{int(thickness*100):02d}"
    obj["span_stations"] = (span_start, span_end)
    obj["chord_fraction"] = (chord_start, chord_end)
    if hinge_fraction is not None:
        obj["hinge_fraction"] = hinge_fraction
        obj["deflection_degrees"] = deflection
    return obj


def hinge_joint(
    component: Component,
    name: str,
    span_start: float,
    span_end: float,
    side: int,
    hinge_fraction: float,
    planform: Planform,
    *,
    camber: float,
    camber_position: float,
    thickness: float,
    travel: str,
) -> bpy.types.Object:
    def center(span: float) -> Vector:
        return (
            airfoil_point(
                span,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=True,
            )
            + airfoil_point(
                span,
                side,
                hinge_fraction,
                planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=False,
            )
        ) * 0.5

    start = center(span_start)
    end = center(span_end)
    return component.joint(
        name,
        tuple(start),
        tuple(end - start),
        joint_type="trailing-edge hinge",
        travel=travel,
    )


def materials() -> dict[str, bpy.types.Material]:
    return {
        "ivory": make_material("Warm aircraft ivory", "F7E6C6", roughness=0.34, coat=0.30),
        "coral": make_material("Coral livery", "ED7168", roughness=0.31, coat=0.32),
        "teal": make_material("Sea-glass teal", "4DB7B6", roughness=0.30, coat=0.32),
        "yellow": make_material("Sunny yellow", "F5C451", roughness=0.30, coat=0.28),
        "glass": make_material("Deep cockpit glass", "28758C", roughness=0.16, metallic=0.04, coat=0.55),
        "glass_glint": make_material("Glass reflection", "BDEBF1", roughness=0.18, coat=0.45),
        "navy": make_material("Detail navy", "1D2B38", roughness=0.38, coat=0.18),
        "rubber": make_material("Aircraft tire rubber", "17222B", roughness=0.62, coat=0.05),
        "metal": make_material("Brushed aluminum", "AAB8BE", roughness=0.28, metallic=0.72, coat=0.20),
        "dark_metal": make_material("Exhaust metal", "46545A", roughness=0.36, metallic=0.65),
        "white": make_material("Eye white", "FFFDF6", roughness=0.32, coat=0.24),
        "pink": make_material("Warm blush", "F4A1A3", roughness=0.36, coat=0.20),
        "red_light": make_emissive_material("Left navigation red", "FF4F5E", 5.0),
        "green_light": make_emissive_material("Right navigation green", "4FE39A", 5.0),
        "white_light": make_emissive_material("Landing light", "FFF6CC", 6.0),
        "platform": make_material("Cloud-blue apron", "AFCFDF", roughness=0.56, coat=0.10),
        "platform_trim": make_material("Apron trim", "6F99B1", roughness=0.43, coat=0.18),
        "cloud": make_material("Soft cloud", "FFFDF8", roughness=0.72, coat=0.04),
    }


def build_fuselage(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    sections = [
        (-2.72, 1.78, 0.34, 0.34, 2.00),
        (-2.55, 1.76, 0.53, 0.45, 2.05),
        (-2.30, 1.74, 0.66, 0.50, 2.10),
        (-1.92, 1.74, 0.74, 0.52, 2.25),
        (-1.66, 1.78, 0.77, 0.60, 2.45),
        (-1.34, 1.88, 0.80, 0.76, 2.75),
        (-0.88, 1.91, 0.82, 0.83, 3.10),
        (-0.28, 1.92, 0.83, 0.84, 3.15),
        (0.30, 1.90, 0.80, 0.78, 3.00),
        (0.76, 1.86, 0.70, 0.65, 2.65),
        (1.20, 1.80, 0.60, 0.55, 2.35),
        (1.65, 1.75, 0.48, 0.43, 2.20),
        (2.05, 1.71, 0.35, 0.33, 2.10),
        (2.40, 1.69, 0.23, 0.24, 2.05),
        (2.70, 1.70, 0.13, 0.15, 2.00),
        (2.90, 1.72, 0.055, 0.085, 2.00),
    ]
    component.add(loft_fuselage(sections, mat["ivory"]))
    for side, label in ((-1, "Near"), (1, "Far")):
        component.add(
            add_curve(
                f"{label}_Firewall_Cowling_Seam",
                [
                    (-1.43, side * 0.68, 2.20),
                    (-1.43, side * 0.79, 1.86),
                    (-1.43, side * 0.66, 1.45),
                ],
                mat["coral"],
                bevel_depth=0.010,
            )
        )
    component.add(profile_ring("Cowling_Nose_Seam", -2.49, 1.75, 0.57, 0.47, 2.05, mat["teal"], 0.010))

    for side, label in ((-1, "Near"), (1, "Far")):
        stripe_points = [
            (-2.46, side * 0.52, 1.57),
            (-1.72, side * 0.72, 1.52),
            (-0.72, side * 0.83, 1.50),
            (0.32, side * 0.80, 1.52),
            (1.30, side * 0.57, 1.57),
            (2.25, side * 0.28, 1.66),
        ]
        component.add(add_curve(f"{label}_Teal_Livery", stripe_points, mat["teal"], bevel_depth=0.032))
        component.add(
            add_curve(
                f"{label}_Coral_Pinstripe",
                [(x, y * 1.005, z + 0.105) for x, y, z in stripe_points],
                mat["coral"],
                bevel_depth=0.009,
            )
        )

    access_panel = add_extruded_xz_shape(
        "Near_Cowling_Access_Panel",
        [(-2.27, 1.68), (-1.61, 1.68), (-1.61, 2.13), (-2.27, 2.13)],
        -0.748,
        0.008,
        mat["ivory"],
        bevel_width=0.020,
    )
    component.add(access_panel)
    for index, x in enumerate((-2.12, -1.82), start=1):
        component.add(
            add_beveled_cube(
                f"Cowling_Cooling_Slot_{index}",
                (x, -0.771, 1.86),
                (0.24, 0.032, 0.055),
                mat["navy"],
                bevel=0.025,
            )
        )
    component.add(
        add_curve(
            "Engine_Exhaust",
            [(-1.77, -0.46, 1.25), (-1.75, -0.50, 1.06), (-1.56, -0.54, 0.98)],
            mat["dark_metal"],
            bevel_depth=0.060,
        )
    )

    hardpoint(
        component,
        "HP_ENGINE_FIREWALL_UPPER",
        (-1.43, 0.0, 2.22),
        "engine mount upper fitting",
        "engine mount -> firewall frame -> fuselage longerons",
    )
    hardpoint(
        component,
        "HP_ENGINE_FIREWALL_LOWER",
        (-1.43, 0.0, 1.42),
        "engine mount lower fitting",
        "engine mount -> firewall frame -> fuselage longerons",
    )
    hardpoint(
        component,
        "HP_EMPENNAGE_FRAME",
        (2.05, 0.0, 1.79),
        "empennage attachment frame",
        "tail loads -> aft bulkhead -> fuselage shell",
    )


def windshield_patch(
    component: Component,
    mat: dict[str, bpy.types.Material],
) -> Vector:
    rows = 7
    columns = 13
    normal = Vector((-0.56, 0.0, 0.83)).normalized()
    half_thickness = 0.012
    vertices: list[tuple[float, float, float]] = []
    for layer_sign in (1.0, -1.0):
        for row in range(rows):
            v = row / (rows - 1)
            for column in range(columns):
                u = -1.0 + 2.0 * column / (columns - 1)
                y = u * (0.45 + 0.21 * v)
                x = (
                    -1.95
                    + 0.68 * (v**0.85)
                    + 0.20 * u * u * (1.0 - 0.25 * v)
                )
                z = 2.29 + 0.37 * v - 0.018 * u * u
                coordinate = Vector((x, y, z)) + normal * half_thickness * layer_sign
                vertices.append(tuple(coordinate))

    layer_size = rows * columns

    def vertex(front: bool, row: int, column: int) -> int:
        return (0 if front else layer_size) + row * columns + column

    faces: list[tuple[int, ...]] = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            faces.append(
                (
                    vertex(True, row, column),
                    vertex(True, row + 1, column),
                    vertex(True, row + 1, column + 1),
                    vertex(True, row, column + 1),
                )
            )
            faces.append(
                (
                    vertex(False, row, column + 1),
                    vertex(False, row + 1, column + 1),
                    vertex(False, row + 1, column),
                    vertex(False, row, column),
                )
            )
    for column in range(columns - 1):
        faces.append(
            (
                vertex(True, 0, column + 1),
                vertex(True, 0, column),
                vertex(False, 0, column),
                vertex(False, 0, column + 1),
            )
        )
        faces.append(
            (
                vertex(True, rows - 1, column),
                vertex(True, rows - 1, column + 1),
                vertex(False, rows - 1, column + 1),
                vertex(False, rows - 1, column),
            )
        )
    for row in range(rows - 1):
        faces.append(
            (
                vertex(True, row, 0),
                vertex(False, row, 0),
                vertex(False, row + 1, 0),
                vertex(True, row + 1, 0),
            )
        )
        faces.append(
            (
                vertex(True, row, columns - 1),
                vertex(True, row + 1, columns - 1),
                vertex(False, row + 1, columns - 1),
                vertex(False, row, columns - 1),
            )
        )
    glass = mesh_object("Continuous_Curved_Windshield", vertices, faces, mat["glass"])
    triangulate = glass.modifiers.new("Stable windshield triangulation", "TRIANGULATE")
    triangulate.quad_method = "BEAUTY"
    triangulate.ngon_method = "BEAUTY"
    glass["integration"] = "single curved glazing patch following the forward cabin loft"
    component.add(glass)
    return normal


def build_cabin(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    window_shapes = [
        ("Door_Window", [(-1.08, 2.05), (-0.98, 2.58), (-0.15, 2.60), (-0.10, 2.03)]),
        ("Rear_Window", [(-0.02, 2.03), (0.00, 2.58), (0.58, 2.43), (0.61, 1.99)]),
    ]
    for side, label in ((-1, "Near"), (1, "Far")):
        for window_name, points in window_shapes:
            component.add(
                add_extruded_xz_shape(
                    f"{label}_{window_name}",
                    points,
                    side * 0.816,
                    0.014,
                    mat["glass"],
                    bevel_width=0.025,
                )
            )
        component.add(
            add_beveled_cube(
                f"{label}_Cabin_B_Pillar",
                (-0.075, side * 0.829, 2.30),
                (0.055, 0.018, 0.58),
                mat["ivory"],
                bevel=0.018,
            )
        )

    normal = windshield_patch(component, mat)
    component.add(
        beam(
            "Windshield_Center_Mullion",
            (-1.90, 0.0, 2.29),
            (-1.25, 0.0, 2.66),
            0.025,
            0.025,
            mat["ivory"],
            bevel=0.012,
        )
    )

    eye_base = Vector((-1.500, 0.0, 2.490)) + normal * 0.030
    for index, y in enumerate((-0.250, 0.250), start=1):
        eye = add_uv_sphere(
            f"Windshield_Eye_{index}",
            (eye_base.x, y, eye_base.z),
            (0.032, 0.145, 0.165),
            mat["white"],
            segments=40,
        )
        eye.rotation_euler.y = math.radians(56.0)
        component.add(eye)
        pupil_center = Vector((eye_base.x, y - 0.020, eye_base.z - 0.010)) + normal * 0.028
        pupil = add_uv_sphere(
            f"Windshield_Pupil_{index}",
            tuple(pupil_center),
            (0.020, 0.072, 0.100),
            mat["navy"],
            segments=36,
        )
        pupil.rotation_euler.y = math.radians(56.0)
        component.add(pupil)
        glint = add_uv_sphere(
            f"Windshield_Glint_{index}",
            tuple(pupil_center + normal * 0.020 + Vector((0.0, -0.022, 0.040))),
            (0.013, 0.022, 0.028),
            mat["white"],
            segments=24,
        )
        glint.rotation_euler.y = math.radians(56.0)
        component.add(glint)

    component.add(
        polyline(
            "Near_Cabin_Door_Seam",
            [
                (-1.13, -0.848, 1.20),
                (-1.14, -0.848, 2.64),
                (-0.08, -0.848, 2.64),
                (-0.05, -0.848, 1.22),
            ],
            mat["coral"],
            bevel=0.007,
            cyclic=True,
        )
    )
    component.add(
        add_beveled_cube(
            "Near_Door_Handle",
            (-0.35, -0.875, 1.76),
            (0.27, 0.045, 0.062),
            mat["navy"],
            bevel=0.025,
        )
    )
    component.add(
        beam(
            "Near_Cabin_Entry_Step",
            (-0.62, -0.83, 1.10),
            (-0.62, -1.13, 1.06),
            0.075,
            0.075,
            mat["metal"],
            bevel=0.025,
        )
    )
    component.joint(
        "JNT_NEAR_CABIN_DOOR",
        (-1.14, -0.848, 1.82),
        (0.0, 0.0, 1.0),
        joint_type="vertical door hinge",
        travel="0 to 75 degrees outward",
    )


def build_wings(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    camber = 0.02
    camber_position = 0.40
    thickness = 0.12
    for side, label in ((-1, "Right_Near"), (1, "Left_Far")):
        component.add(
            airfoil_segment(
                f"{label}_Fixed_Wing",
                0.0,
                3.98,
                side,
                0.001,
                WING_HINGE,
                mat["ivory"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Fixed_Wingtip",
                3.98,
                WING_HALF_SPAN,
                side,
                0.001,
                WING_HINGE,
                mat["coral"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Root_Trailing_Bay",
                0.0,
                0.76,
                side,
                WING_HINGE + 0.014,
                0.995,
                mat["ivory"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Inboard_Flap",
                0.82,
                2.34,
                side,
                WING_HINGE + 0.018,
                0.995,
                mat["ivory"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                hinge_fraction=WING_HINGE,
                deflection=0.0,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Outboard_Aileron",
                2.42,
                3.92,
                side,
                WING_HINGE + 0.018,
                0.995,
                mat["ivory"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                hinge_fraction=WING_HINGE,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Wingtip_Trailing_Cap",
                3.98,
                WING_HALF_SPAN,
                side,
                WING_HINGE + 0.014,
                0.995,
                mat["coral"],
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
            )
        )
        hinge_joint(
            component,
            f"JNT_{label}_FLAP",
            0.82,
            2.34,
            side,
            WING_HINGE,
            wing_planform,
            camber=camber,
            camber_position=camber_position,
            thickness=thickness,
            travel="0 to 30 degrees down",
        )
        hinge_joint(
            component,
            f"JNT_{label}_AILERON",
            2.42,
            3.92,
            side,
            WING_HINGE,
            wing_planform,
            camber=camber,
            camber_position=camber_position,
            thickness=thickness,
            travel="18 degrees up / 12 degrees down",
        )
        for seam_start, seam_end, seam_name in (
            (0.82, 2.34, "Flap"),
            (2.42, 3.92, "Aileron"),
        ):
            start = airfoil_point(
                seam_start,
                side,
                WING_HINGE,
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=True,
            )
            end = airfoil_point(
                seam_end,
                side,
                WING_HINGE,
                wing_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                upper=True,
            )
            component.add(
                add_cylinder_between(
                    f"{label}_{seam_name}_Hinge_Seam",
                    tuple(start + Vector((0.0, 0.0, 0.006))),
                    tuple(end + Vector((0.0, 0.0, 0.006))),
                    0.005,
                    mat["navy"],
                )
            )

        lower_attach = (0.02, side * 0.72, 1.40)
        _, _, attach_z = wing_planform(2.62)
        upper_attach = (-0.18, side * 2.62, attach_z - 0.105)
        component.add(
            beam(
                f"{label}_Lift_Strut",
                lower_attach,
                upper_attach,
                0.115,
                0.16,
                mat["ivory"],
                bevel=0.045,
            )
        )
        for suffix, position in (("Lower", lower_attach), ("Upper", upper_attach)):
            component.add(
                add_uv_sphere(
                    f"{label}_Strut_{suffix}_Fitting",
                    position,
                    (0.13, 0.13, 0.13),
                    mat["metal"],
                    segments=28,
                )
            )
        hardpoint(
            component,
            f"HP_{label}_STRUT_LOWER",
            lower_attach,
            "lift-strut lower fitting",
            "wing bending -> lift strut -> reinforced fuselage frame",
        )
        hardpoint(
            component,
            f"HP_{label}_STRUT_UPPER",
            upper_attach,
            "lift-strut upper fitting",
            "wing spar -> lift strut -> fuselage frame",
        )

    component.add(
        add_uv_sphere(
            "Wing_Carrythrough_Roof_Fairing",
            (-0.05, 0.0, 2.61),
            (1.08, 1.02, 0.17),
            mat["ivory"],
            segments=40,
        )
    )

    for side, label in ((-1, "Right"), (1, "Left")):
        leading, chord, center_z = wing_planform(1.22)
        component.add(
            add_cylinder(
                f"{label}_Wing_Fuel_Cap",
                (leading + chord * 0.38, side * 1.22, center_z + chord * 0.085),
                0.075,
                0.028,
                mat["coral"],
                vertices=36,
            )
        )

    leading, _, center_z = wing_planform(2.75)
    component.add(
        add_uv_sphere(
            "Right_Wing_Landing_Light",
            (leading + 0.035, -2.75, center_z),
            (0.040, 0.085, 0.055),
            mat["white_light"],
            segments=32,
        )
    )
    leading, chord, center_z = wing_planform(WING_HALF_SPAN)
    component.add(
        add_uv_sphere(
            "Right_Navigation_Green",
            (leading + chord * 0.62, -(WING_HALF_SPAN + 0.035), center_z),
            (0.085, 0.070, 0.070),
            mat["green_light"],
            segments=32,
        )
    )
    component.add(
        add_uv_sphere(
            "Left_Navigation_Red",
            (leading + chord * 0.62, WING_HALF_SPAN + 0.035, center_z),
            (0.085, 0.070, 0.070),
            mat["red_light"],
            segments=32,
        )
    )

    component.add(
        add_cylinder_between(
            "Pitot_Vertical_Leg",
            (-0.70, -2.95, 2.73),
            (-0.70, -2.95, 2.55),
            0.025,
            mat["metal"],
        )
    )
    component.add(
        add_cylinder_between(
            "Pitot_Forward_Tube",
            (-0.70, -2.95, 2.55),
            (-1.10, -2.95, 2.55),
            0.025,
            mat["metal"],
        )
    )

    leading, chord, center_z = wing_planform(0.0)
    for spar_name, chord_fraction in (("FRONT", 0.25), ("REAR", 0.66)):
        hardpoint(
            component,
            f"HP_WING_CARRYTHROUGH_{spar_name}",
            (leading + chord * chord_fraction, 0.0, center_z),
            f"{spar_name.lower()} spar carry-through",
            "left spar -> cabin carry-through frame -> right spar",
        )


def build_tail(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    camber = 0.0
    camber_position = 0.40
    thickness = 0.10
    for side, label in ((-1, "Right_Near"), (1, "Left_Far")):
        component.add(
            airfoil_segment(
                f"{label}_Horizontal_Stabilizer",
                0.0,
                TAIL_HALF_SPAN,
                side,
                0.001,
                TAIL_HINGE,
                mat["ivory"],
                tail_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
            )
        )
        component.add(
            airfoil_segment(
                f"{label}_Elevator",
                0.10,
                1.45,
                side,
                TAIL_HINGE + 0.020,
                0.995,
                mat["ivory"],
                tail_planform,
                camber=camber,
                camber_position=camber_position,
                thickness=thickness,
                hinge_fraction=TAIL_HINGE,
                deflection=0.0,
            )
        )
        hinge_joint(
            component,
            f"JNT_{label}_ELEVATOR",
            0.10,
            1.45,
            side,
            TAIL_HINGE,
            tail_planform,
            camber=camber,
            camber_position=camber_position,
            thickness=thickness,
            travel="25 degrees up / 20 degrees down",
        )

    component.add(
        add_uv_sphere(
            "Empennage_Root_Fillet",
            (1.84, 0.0, 1.99),
            (0.72, 0.31, 0.23),
            mat["ivory"],
            segments=40,
        )
    )
    component.add(
        add_extruded_xz_shape(
            "Vertical_Stabilizer_Fixed",
            [
                (1.56, 1.78),
                (2.61, 1.82),
                (2.57, 3.33),
                (2.27, 3.55),
                (1.82, 2.20),
            ],
            0.0,
            0.19,
            mat["ivory"],
            bevel_width=0.085,
        )
    )
    rudder = add_extruded_xz_shape(
        "Rudder_Movable",
        [(2.64, 1.84), (3.02, 1.78), (2.98, 3.05), (2.60, 3.31)],
        0.0,
        0.17,
        mat["coral"],
        bevel_width=0.075,
    )
    component.add(rudder)
    joint = component.joint(
        "JNT_RUDDER",
        (2.62, 0.0, 1.86),
        (-0.03, 0.0, 1.0),
        joint_type="vertical tail hinge line",
        travel="25 degrees left / right",
    )
    joint["attached_component"] = rudder.name

    component.add(
        add_beveled_cube(
            "Near_Elevator_Trim_Tab",
            (2.82, -0.78, 2.03),
            (0.25, 0.42, 0.035),
            mat["coral"],
            bevel=0.025,
        )
    )
    component.joint(
        "JNT_ELEVATOR_TRIM_TAB",
        (2.70, -0.78, 2.03),
        (0.0, 1.0, 0.0),
        joint_type="trim-tab hinge",
        travel="plus/minus 18 degrees",
    )
    component.add(
        add_uv_sphere(
            "Tail_White_Position_Light",
            (2.65, 0.0, 3.43),
            (0.055, 0.055, 0.055),
            mat["white_light"],
            segments=28,
        )
    )


def propeller_blade(
    component: Component,
    name: str,
    angle: float,
    mat: dict[str, bpy.types.Material],
    joint: bpy.types.Object,
) -> None:
    blade = add_local_yz_prism(
        name,
        [
            (-0.09, 0.20),
            (-0.18, 0.58),
            (-0.13, 1.08),
            (0.12, 1.03),
            (0.18, 0.55),
            (0.09, 0.20),
        ],
        0.105,
        (-3.19, 0.0, PROP_Z),
        mat["coral"],
        rotation_x=angle,
        bevel_width=0.055,
    )
    component.add(blade)
    parent_keep_world(blade, joint)
    tip = add_local_yz_prism(
        f"{name}_Tip",
        [(-0.13, 0.88), (-0.13, 1.08), (0.12, 1.03), (0.14, 0.87)],
        0.112,
        (-3.19, 0.0, PROP_Z),
        mat["yellow"],
        rotation_x=angle,
        bevel_width=0.035,
    )
    component.add(tip)
    parent_keep_world(tip, joint)


def build_engine(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    prop_joint = component.joint(
        "JNT_PROPELLER_SHAFT",
        (-3.18, 0.0, PROP_Z),
        (1.0, 0.0, 0.0),
        joint_type="propeller shaft bearing",
        travel="continuous rotation about aircraft X axis",
    )
    shaft = add_cylinder(
        "Propeller_Shaft",
        (-2.96, 0.0, PROP_Z),
        0.16,
        0.48,
        mat["metal"],
        rotation=(0.0, math.radians(90.0), 0.0),
        vertices=40,
    )
    component.add(shaft)
    parent_keep_world(shaft, prop_joint)
    hub = add_cylinder(
        "Propeller_Hub",
        (-3.17, 0.0, PROP_Z),
        0.28,
        0.18,
        mat["metal"],
        rotation=(0.0, math.radians(90.0), 0.0),
        vertices=48,
    )
    component.add(hub)
    parent_keep_world(hub, prop_joint)
    for index, angle in enumerate((math.radians(22.0), math.radians(202.0)), start=1):
        propeller_blade(component, f"Propeller_Blade_{index}", angle, mat, prop_joint)
    spinner = add_uv_sphere(
        "Rounded_Propeller_Spinner",
        (-3.35, 0.0, PROP_Z),
        (0.32, 0.35, 0.35),
        mat["yellow"],
        segments=48,
    )
    component.add(spinner)
    parent_keep_world(spinner, prop_joint)

    smile = add_curve(
        "Cowling_Smile_Cooling_Intake",
        [(-2.705, -0.34, 1.55), (-2.735, 0.0, 1.41), (-2.705, 0.34, 1.55)],
        mat["navy"],
        bevel_depth=0.052,
    )
    smile["functional_detail"] = "lower cowling cooling inlet shaped as expression"
    component.add(smile)


def wheel(
    component: Component,
    name: str,
    location: tuple[float, float, float],
    major: float,
    minor: float,
    side: int,
    mat: dict[str, bpy.types.Material],
) -> tuple[bpy.types.Object, bpy.types.Object]:
    tire = add_torus(
        f"{name}_Tire",
        location,
        major,
        minor,
        mat["rubber"],
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    component.add(tire)
    hub = add_cylinder(
        f"{name}_Hub",
        (location[0], location[1] + side * minor * 0.80, location[2]),
        major * 0.43,
        minor * 1.85,
        mat["yellow"],
        rotation=(math.radians(90.0), 0.0, 0.0),
        vertices=40,
    )
    component.add(hub)
    tire["ground_contact_z"] = GROUND_Z
    tire["rolling_axis"] = (0.0, 1.0, 0.0)
    return tire, hub


def build_gear(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    main_radius = 0.43
    for side, label in ((-1, "Right_Near"), (1, "Left_Far")):
        wheel_location = (0.16, side * 1.12, GROUND_Z + main_radius)
        tire, hub = wheel(component, f"{label}_Main", wheel_location, 0.29, 0.14, side, mat)
        attachment = (0.02, side * 0.58, 1.22)
        component.add(
            beam(
                f"{label}_Spring_Gear_Leg",
                attachment,
                (0.16, side * 1.12, 0.57),
                0.13,
                0.18,
                mat["metal"],
                bevel=0.040,
            )
        )
        pant = add_uv_sphere(
            f"{label}_Wheel_Pant",
            (0.14, side * 1.12, 0.68),
            (0.55, 0.255, 0.32),
            mat["ivory"],
            segments=40,
        )
        pant.rotation_euler.y = math.radians(-4.0)
        component.add(pant)
        outer_y = side * (1.12 + 0.258)
        component.add(
            add_beveled_cube(
                f"{label}_Pant_Stripe",
                (0.10, outer_y, 0.69),
                (0.42, 0.025, 0.075),
                mat["coral"],
                bevel=0.025,
            )
        )
        hardpoint(
            component,
            f"HP_{label}_MAIN_GEAR",
            attachment,
            "main gear reinforced attachment",
            "wheel impact -> spring leg -> lower cabin bulkhead",
        )
        joint = component.joint(
            f"JNT_{label}_MAIN_WHEEL",
            wheel_location,
            (0.0, 1.0, 0.0),
            joint_type="wheel axle",
            travel="continuous wheel rotation",
        )
        tire["joint"] = joint.name
        hub["joint"] = joint.name

    nose_location = (-2.02, -0.02, GROUND_Z + 0.34)
    nose_tire, nose_hub = wheel(component, "Nose", nose_location, 0.23, 0.11, -1, mat)
    upper = (-1.92, 0.0, 1.22)
    lower = (-2.02, 0.0, 0.53)
    component.add(add_cylinder_between("Nose_Gear_Oleo", upper, lower, 0.075, mat["metal"]))
    for side in (-1, 1):
        component.add(
            add_cylinder_between(
                f"Nose_Gear_Fork_{'Near' if side < 0 else 'Far'}",
                (-2.02, side * 0.075, 0.55),
                (-2.02, side * 0.145, 0.35),
                0.045,
                mat["metal"],
            )
        )
    component.add(
        add_uv_sphere(
            "Nose_Wheel_Pant",
            (-2.00, -0.02, 0.53),
            (0.43, 0.21, 0.25),
            mat["coral"],
            segments=36,
        )
    )
    hardpoint(
        component,
        "HP_NOSE_GEAR_FIREWALL",
        upper,
        "nose gear / engine mount attachment",
        "nose wheel impact -> oleo -> engine mount / firewall",
    )
    steering = component.joint(
        "JNT_NOSE_GEAR_STEERING",
        lower,
        (0.0, 0.0, 1.0),
        joint_type="steerable nose strut",
        travel="plus/minus 12 degrees",
    )
    axle = component.joint(
        "JNT_NOSE_WHEEL",
        nose_location,
        (0.0, 1.0, 0.0),
        joint_type="wheel axle",
        travel="continuous wheel rotation",
    )
    nose_tire["steering_joint"] = steering.name
    nose_tire["wheel_joint"] = axle.name
    nose_hub["wheel_joint"] = axle.name


def build_details(component: Component, mat: dict[str, bpy.types.Material]) -> None:
    component.add(
        add_extruded_xz_shape(
            "VHF_Antenna",
            [(0.76, 2.47), (0.90, 2.47), (0.83, 2.88)],
            0.0,
            0.055,
            mat["navy"],
            bevel_width=0.028,
        )
    )
    for index, location in enumerate(((0.76, -0.718, 1.81), (0.76, 0.718, 1.81)), start=1):
        component.add(
            add_uv_sphere(
                f"Static_Port_{index}",
                location,
                (0.035, 0.018, 0.035),
                mat["metal"],
                segments=20,
            )
        )
    for x, z, label in ((-2.38, 2.07, "Forward"), (-1.60, 2.10, "Aft")):
        component.add(
            add_uv_sphere(
                f"Cowling_{label}_Camloc",
                (x, -0.758, z),
                (0.032, 0.018, 0.032),
                mat["metal"],
                segments=20,
            )
        )


def build_presentation(mat: dict[str, bpy.types.Material]) -> None:
    scene = bpy.context.scene
    apron = add_cylinder(
        "Display_Apron",
        (0.0, 0.0, -0.24),
        5.35,
        0.48,
        mat["platform"],
        vertices=128,
    )
    apron["top_surface_z"] = GROUND_Z
    add_torus(
        "Display_Apron_Trim",
        (0.0, 0.0, -0.13),
        5.23,
        0.065,
        mat["platform_trim"],
        scale=(1.0, 1.0, 0.72),
    )
    add_cloud("Background_Cloud_Left", (2.8, 4.2, 3.25), 0.62, mat["cloud"])
    add_cloud("Background_Cloud_Right", (-3.3, 3.8, 3.70), 0.52, mat["cloud"])

    bpy.ops.object.camera_add(location=(-10.2, -8.8, 5.3))
    camera = bpy.context.object
    camera.name = "Camera_Hero_ThreeQuarter"
    camera.data.type = "PERSP"
    camera.data.lens = 54
    camera.data.sensor_width = 36
    point_at(camera, (-0.20, 0.0, 1.66))
    scene.camera = camera

    def area_light(
        name: str,
        location: tuple[float, float, float],
        energy: float,
        size: float,
        color: str,
        target: tuple[float, float, float],
    ) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = hex_color(color)[:3]
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        bpy.context.collection.objects.link(obj)
        point_at(obj, target)

    area_light("Key_Softbox", (-5.5, -7.2, 10.5), 1150.0, 5.0, "FFF0D0", (0.0, 0.0, 1.6))
    area_light("Fill_Softbox", (5.5, -3.0, 6.3), 760.0, 4.5, "C7E9FF", (0.0, 0.0, 1.6))
    area_light("Wing_Rim_Light", (1.5, 6.0, 8.5), 920.0, 4.0, "FFD6D0", (0.0, 0.0, 2.2))
    sun_data = bpy.data.lights.new("Soft_Sun", "SUN")
    sun_data.energy = 0.65
    sun_data.angle = math.radians(15.0)
    sun = bpy.data.objects.new("Soft_Sun", sun_data)
    sun.rotation_euler = (math.radians(24.0), math.radians(-20.0), math.radians(-32.0))
    bpy.context.collection.objects.link(sun)


def configure_scene() -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.filepath = str(RENDER_PATH)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.15
    scene.view_settings.gamma = 1.0
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("Sky_World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = hex_color("BFD7E7")
        background.inputs["Strength"].default_value = 0.55


def create_cartoon_trainer() -> None:
    clear_scene()
    configure_scene()
    mat = materials()

    master = bpy.data.collections.new("CLOUDHOPPER_TRAINER_V3")
    bpy.context.scene.collection.children.link(master)
    aircraft_root = bpy.data.objects.new("AIRCRAFT_DATUM_ROOT", None)
    aircraft_root.empty_display_type = "ARROWS"
    aircraft_root.empty_display_size = 0.45
    master.objects.link(aircraft_root)
    aircraft_root["coordinate_system"] = "X aft / Y span / Z up; nose points toward negative X"
    aircraft_root["archetype"] = "high-wing, strut-braced, single-engine tricycle trainer"
    aircraft_root["proportion_basis"] = "real trainer wingspan:length ratio, cartoon-compressed cabin and nose"

    fuselage = Component("01_FUSELAGE_AIRFRAME", master, aircraft_root)
    cabin = Component("02_CABIN_AND_CHARACTER", master, aircraft_root)
    wings = Component("03_WING_ASSEMBLY", master, aircraft_root)
    tail = Component("04_EMPENNAGE", master, aircraft_root)
    engine = Component("05_ENGINE_AND_PROPELLER", master, aircraft_root)
    gear = Component("06_TRICYCLE_LANDING_GEAR", master, aircraft_root)
    details = Component("07_SYSTEM_DETAILS", master, aircraft_root)

    build_fuselage(fuselage, mat)
    build_cabin(cabin, mat)
    build_wings(wings, mat)
    build_tail(tail, mat)
    build_engine(engine, mat)
    build_gear(gear, mat)
    build_details(details, mat)
    build_presentation(mat)

    scene = bpy.context.scene
    scene["artwork_title"] = "Cloudhopper — Mechanically Coherent Cartoon Trainer"
    scene["construction_logic"] = (
        "Frame-station fuselage; cambered spar/rib wing volume; inboard flaps; outboard ailerons; "
        "hinged elevator and rudder; firewall engine/nose-gear loads; cabin-bulkhead main-gear loads."
    )
    scene["character_logic"] = "Eyes sit in the windshield; the smile is also a lower cowling cooling inlet."
    scene["ground_contact_datum_z"] = GROUND_Z

    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.render.render(write_still=True)
    joints = [obj for obj in bpy.data.objects if obj.name.startswith("JNT_")]
    hardpoints = [obj for obj in bpy.data.objects if obj.name.startswith("HP_")]
    print(
        f"CLOUDHOPPER_V3_COMPLETE objects={len(bpy.data.objects)} "
        f"joints={len(joints)} hardpoints={len(hardpoints)} "
        f"blend={BLEND_PATH} render={RENDER_PATH}"
    )


if __name__ == "__main__":
    create_cartoon_trainer()

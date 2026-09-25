from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cute_airplane import (  # noqa: E402
    add_beveled_cube,
    add_cloud,
    add_curve,
    add_cylinder,
    add_cylinder_between,
    add_extruded_xy_shape,
    add_extruded_xz_shape,
    add_uv_sphere,
    assign_material,
    hex_color,
    make_material,
    point_at,
    smooth,
)


BLEND_PATH = SCRIPT_DIR / "cute_airplane_detailed.blend"
RENDER_PATH = SCRIPT_DIR / "cute_airplane_detailed.png"
PLANE_Z = 1.45
PLATFORM_TOP_Z = -0.32
MAIN_WHEEL_RADIUS = 0.31
NOSE_WHEEL_RADIUS = 0.25
MAIN_WHEEL_Z = PLATFORM_TOP_Z + MAIN_WHEEL_RADIUS
NOSE_WHEEL_Z = PLATFORM_TOP_Z + NOSE_WHEEL_RADIUS


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


def make_glass_material(name: str, color: str) -> bpy.types.Material:
    material = make_material(name, color, roughness=0.14, coat=0.65)
    material.diffuse_color = (*hex_color(color)[:3], 0.62)
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        alpha = principled.inputs.get("Alpha")
        transmission = principled.inputs.get("Transmission Weight")
        if alpha is not None:
            alpha.default_value = 0.62
        if transmission is not None:
            transmission.default_value = 0.25
    try:
        material.surface_render_method = "DITHERED"
    except (AttributeError, TypeError):
        pass
    return material


def make_emissive_material(name: str, color: str, strength: float = 4.0) -> bpy.types.Material:
    material = make_material(name, color, roughness=0.25, coat=0.35)
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        emission_color = principled.inputs.get("Emission Color")
        emission_strength = principled.inputs.get("Emission Strength")
        if emission_color is not None:
            emission_color.default_value = hex_color(color)
        if emission_strength is not None:
            emission_strength.default_value = strength
    return material


def new_collection(name: str, parent: bpy.types.Collection) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in tuple(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


class Component:
    def __init__(
        self,
        name: str,
        parent_collection: bpy.types.Collection,
        aircraft_root: bpy.types.Object,
    ) -> None:
        self.collection = new_collection(name, parent_collection)
        self.root = bpy.data.objects.new(f"{name}_ASSEMBLY", None)
        self.root.empty_display_type = "CUBE"
        self.root.empty_display_size = 0.22
        self.collection.objects.link(self.root)
        self.root.parent = aircraft_root

    def add(self, obj: bpy.types.Object) -> bpy.types.Object:
        move_to_collection(obj, self.collection)
        obj.parent = self.root
        return obj

    def joint(
        self,
        name: str,
        location: tuple[float, float, float],
        axis: tuple[float, float, float],
        *,
        joint_type: str,
        travel: str,
    ) -> bpy.types.Object:
        joint = bpy.data.objects.new(name, None)
        joint.empty_display_type = "ARROWS"
        joint.empty_display_size = 0.16
        joint.location = location
        direction = Vector(axis).normalized()
        up_axis = "X" if abs(direction.dot(Vector((0.0, 1.0, 0.0)))) > 0.9 else "Y"
        joint.rotation_mode = "QUATERNION"
        joint.rotation_quaternion = direction.to_track_quat("Z", up_axis)
        joint["joint_type"] = joint_type
        joint["axis_local"] = "Z"
        joint["axis_world"] = tuple(round(value, 6) for value in direction)
        joint["travel"] = travel
        joint.hide_render = True
        self.collection.objects.link(joint)
        joint.parent = self.root
        return joint


def parent_keep_world(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    world_matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = world_matrix


def add_torus(
    name: str,
    location: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    material: bpy.types.Material,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_segments=64,
        minor_segments=16,
        location=location,
        rotation=rotation,
        major_radius=major_radius,
        minor_radius=minor_radius,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign_material(obj, material)
    smooth(obj)
    return obj


def add_local_yz_prism(
    name: str,
    points: list[tuple[float, float]],
    thickness: float,
    location: tuple[float, float, float],
    material: bpy.types.Material,
    *,
    rotation_x: float = 0.0,
    bevel_width: float = 0.06,
) -> bpy.types.Object:
    half = thickness * 0.5
    vertices = [(-half, y, z) for y, z in points]
    vertices.extend((half, y, z) for y, z in points)
    count = len(points)
    faces: list[tuple[int, ...]] = [
        tuple(range(count)),
        tuple(reversed(range(count, count * 2))),
    ]
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, next_index + count, index + count))

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler.x = rotation_x
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)
    bevel = obj.modifiers.new(name="Blade edge radius", type="BEVEL")
    bevel.width = bevel_width
    bevel.segments = 4
    bevel.limit_method = "ANGLE"
    smooth(obj)
    return obj


def add_star(
    name: str,
    center: tuple[float, float],
    z: float,
    outer_radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    points: list[tuple[float, float]] = []
    for index in range(10):
        angle = math.pi * 0.5 + index * math.pi / 5.0
        radius = outer_radius if index % 2 == 0 else outer_radius * 0.44
        points.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
    return add_extruded_xy_shape(name, points, z, 0.055, material, bevel_width=0.025)


def add_star_xz(
    name: str,
    center: tuple[float, float],
    y: float,
    outer_radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    points: list[tuple[float, float]] = []
    for index in range(10):
        angle = math.pi * 0.5 + index * math.pi / 5.0
        radius = outer_radius if index % 2 == 0 else outer_radius * 0.44
        points.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
    return add_extruded_xz_shape(name, points, y, 0.055, material, bevel_width=0.025)


def add_heart(
    name: str,
    center: tuple[float, float],
    y: float,
    scale: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    points: list[tuple[float, float]] = []
    for index in range(40):
        t = index * math.tau / 40.0
        x = 16.0 * math.sin(t) ** 3
        z = 13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t) - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t)
        points.append((center[0] + x * scale / 17.0, center[1] + z * scale / 17.0))
    return add_extruded_xz_shape(name, points, y, 0.055, material, bevel_width=0.02)


def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "ivory": make_material("V2 Warm Ivory", "FFF1D4", roughness=0.34, coat=0.35),
        "ivory_dark": make_material("V2 Biscuit Seam", "CBAF7B", roughness=0.4, metallic=0.08, coat=0.2),
        "mint": make_material("V2 Mint", "57C9BB", roughness=0.32, coat=0.35),
        "mint_dark": make_material("V2 Deep Mint", "258E8B", roughness=0.3, coat=0.35),
        "coral": make_material("V2 Coral", "F56F83", roughness=0.3, coat=0.38),
        "coral_dark": make_material("V2 Deep Coral", "B94359", roughness=0.32, coat=0.3),
        "blush": make_material("V2 Blush", "F7A5B4", roughness=0.36, coat=0.3),
        "yellow": make_material("V2 Sunshine", "F4C75E", roughness=0.28, metallic=0.05, coat=0.4),
        "navy": make_material("V2 Navy", "17324D", roughness=0.3, metallic=0.05, coat=0.3),
        "tire": make_material("V2 Rubber", "111B2C", roughness=0.58, coat=0.08),
        "blue": make_material("V2 Cockpit Blue", "318CA8", roughness=0.18, metallic=0.07, coat=0.6),
        "blue_light": make_material("V2 Sky Highlight", "A9E8F0", roughness=0.2, coat=0.45),
        "glass": make_glass_material("V2 Canopy Glass", "58B6CB"),
        "white": make_material("V2 Soft White", "FFFDF6", roughness=0.55, coat=0.12),
        "metal": make_material("V2 Champagne Metal", "B8904E", roughness=0.24, metallic=0.58, coat=0.4),
        "steel": make_material("V2 Steel", "8FA1AE", roughness=0.22, metallic=0.7, coat=0.32),
        "platform": make_material("V2 Lavender Platform", "A99BE0", roughness=0.5, coat=0.1),
        "platform_trim": make_material("V2 Platform Trim", "6759AD", roughness=0.4, metallic=0.08, coat=0.15),
        "cloud": make_material("V2 Cloud", "FFFDF8", roughness=0.72, coat=0.02),
        "red_light": make_emissive_material("V2 Port Light", "FF405D", 6.0),
        "green_light": make_emissive_material("V2 Starboard Light", "41E39B", 6.0),
        "white_light": make_emissive_material("V2 Tail Light", "E8FAFF", 7.0),
    }


def build_fuselage(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    ivory = materials["ivory"]
    seam = materials["ivory_dark"]
    coral = materials["coral"]
    metal = materials["metal"]
    navy = materials["navy"]

    component.add(add_uv_sphere("Fuselage_MainShell", (0.0, 0.0, PLANE_Z), (2.5, 0.79, 0.74), ivory, segments=64))
    component.add(add_uv_sphere("Fuselage_TailCone", (1.98, 0.0, PLANE_Z + 0.03), (0.78, 0.45, 0.4), ivory, segments=48))
    component.add(add_uv_sphere("Fuselage_BellyFairing", (0.22, 0.0, PLANE_Z - 0.57), (1.2, 0.52, 0.25), ivory, segments=48))

    # Raised panel breaks follow the changing elliptical fuselage section.
    for index, x_coordinate in enumerate((-1.65, -0.82, 0.08, 0.98, 1.68), start=1):
        cross_section = math.sqrt(max(0.05, 1.0 - (x_coordinate / 2.5) ** 2))
        y_radius = 0.79 * cross_section
        z_radius = 0.74 * cross_section
        base_radius = max(y_radius, z_radius)
        ring = add_torus(
            f"Fuselage_PanelRing_{index}",
            (x_coordinate, 0.0, PLANE_Z),
            base_radius,
            0.018,
            seam,
            rotation=(0.0, math.radians(90.0), 0.0),
            scale=(z_radius / base_radius, y_radius / base_radius, 1.0),
        )
        component.add(ring)

    # A curved lower trim stripe and two tidy rows of fasteners.
    stripe_points: list[tuple[float, float, float]] = []
    for x_coordinate in (-2.0, -1.4, -0.7, 0.0, 0.8, 1.55, 2.05):
        y_surface = -0.79 * math.sqrt(max(0.05, 1.0 - (x_coordinate / 2.5) ** 2))
        stripe_points.append((x_coordinate, y_surface - 0.026, PLANE_Z - 0.29))
    component.add(add_curve("Fuselage_CoralBelt", stripe_points, coral, bevel_depth=0.038))

    for row, z_offset in enumerate((-0.42, 0.42), start=1):
        for index, x_coordinate in enumerate((-1.82, -1.48, -1.12, -0.72, -0.3, 0.14, 0.58, 1.0, 1.38, 1.7), start=1):
            cross_section = math.sqrt(max(0.08, 1.0 - (x_coordinate / 2.5) ** 2))
            y_surface = -0.79 * cross_section * math.sqrt(max(0.05, 1.0 - (z_offset / (0.74 * cross_section)) ** 2))
            rivet = add_uv_sphere(
                f"Fuselage_Rivet_R{row}_{index}",
                (x_coordinate, y_surface - 0.032, PLANE_Z + z_offset),
                (0.034, 0.018, 0.034),
                metal,
                segments=20,
            )
            component.add(rivet)

    # Side service hatch, inset center, hinge, and four bolts.
    hatch_x = 1.38
    hatch_y = -0.66
    hatch_z = PLANE_Z - 0.12
    component.add(
        add_torus(
            "Fuselage_ServiceHatch_Rim",
            (hatch_x, hatch_y, hatch_z),
            0.25,
            0.025,
            seam,
            rotation=(math.radians(90.0), 0.0, 0.0),
            scale=(1.05, 0.72, 1.0),
        )
    )
    component.add(add_uv_sphere("Fuselage_ServiceHatch_Panel", (hatch_x, hatch_y + 0.018, hatch_z), (0.22, 0.038, 0.16), ivory, segments=32))
    component.add(add_cylinder("Fuselage_ServiceHatch_Hinge", (hatch_x - 0.24, hatch_y - 0.025, hatch_z), 0.026, 0.26, metal, rotation=(0.0, 0.0, math.radians(90.0)), vertices=24))
    for index, angle in enumerate((45.0, 135.0, 225.0, 315.0), start=1):
        radians = math.radians(angle)
        component.add(
            add_uv_sphere(
                f"Fuselage_HatchBolt_{index}",
                (hatch_x + math.cos(radians) * 0.2, hatch_y - 0.03, hatch_z + math.sin(radians) * 0.14),
                (0.026, 0.014, 0.026),
                metal,
                segments=18,
            )
        )

    # Chin intake and two cowling-side vents.
    component.add(add_beveled_cube("Fuselage_ChinIntake", (-1.75, -0.08, PLANE_Z - 0.67), (0.46, 0.42, 0.16), navy, bevel=0.075))
    for index, x_coordinate in enumerate((-1.94, -1.66), start=1):
        component.add(add_beveled_cube(f"Fuselage_Vent_{index}", (x_coordinate, -0.665, PLANE_Z - 0.07), (0.22, 0.035, 0.065), navy, bevel=0.025, rotation=(0.0, math.radians(-8.0), 0.0)))

    # A dimensional heart badge is a distinct, editable part.
    component.add(add_heart("Fuselage_HeartBadge", (-0.28, PLANE_Z - 0.28), -0.775, 0.23, coral))
    component.joint(
        "DATUM_Fuselage_Centerline",
        (0.0, 0.0, PLANE_Z),
        (1.0, 0.0, 0.0),
        joint_type="datum",
        travel="longitudinal X axis",
    )


def build_cockpit(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    glass = materials["glass"]
    blue = materials["blue"]
    blue_light = materials["blue_light"]
    navy = materials["navy"]
    coral = materials["coral"]
    yellow = materials["yellow"]
    ivory = materials["ivory"]
    metal = materials["metal"]

    # Two seats and a compact instrument panel remain visible through the canopy.
    for index, y_coordinate in enumerate((-0.23, 0.23), start=1):
        seat_back = add_beveled_cube(
            f"Cockpit_SeatBack_{index}",
            (-0.32, y_coordinate, PLANE_Z + 0.56),
            (0.34, 0.29, 0.46),
            coral,
            bevel=0.1,
            rotation=(0.0, math.radians(-10.0), 0.0),
        )
        component.add(seat_back)
        component.add(add_beveled_cube(f"Cockpit_SeatCushion_{index}", (-0.48, y_coordinate, PLANE_Z + 0.31), (0.44, 0.3, 0.14), ivory, bevel=0.07))
        component.add(add_uv_sphere(f"Cockpit_Headrest_{index}", (-0.2, y_coordinate, PLANE_Z + 0.81), (0.16, 0.14, 0.14), coral, segments=32))

    component.add(add_beveled_cube("Cockpit_InstrumentPanel", (-0.92, 0.0, PLANE_Z + 0.5), (0.14, 0.57, 0.3), navy, bevel=0.07, rotation=(0.0, math.radians(-10.0), 0.0)))
    for index, (y_coordinate, z_offset, material) in enumerate(
        [(-0.18, 0.07, yellow), (0.0, -0.02, blue_light), (0.18, 0.07, coral)],
        start=1,
    ):
        component.add(add_uv_sphere(f"Cockpit_Dial_{index}", (-1.005, y_coordinate, PLANE_Z + 0.52 + z_offset), (0.025, 0.065, 0.065), material, segments=24))

    component.add(add_cylinder_between("Cockpit_ControlStick", (-0.56, -0.17, PLANE_Z + 0.28), (-0.66, -0.17, PLANE_Z + 0.62), 0.035, metal))
    component.add(add_uv_sphere("Cockpit_ControlGrip", (-0.66, -0.17, PLANE_Z + 0.65), (0.085, 0.065, 0.065), navy, segments=28))

    # Canopy shell, lower rim, framing, and fasteners.
    component.add(add_uv_sphere("Cockpit_CanopyShell", (-0.54, 0.0, PLANE_Z + 0.67), (0.86, 0.62, 0.48), glass, segments=64))
    component.add(add_torus("Cockpit_BaseRim", (-0.54, 0.0, PLANE_Z + 0.41), 0.61, 0.045, blue, scale=(1.36, 0.88, 1.0)))
    component.add(add_curve("Cockpit_NearFrame", [(-1.05, -0.49, PLANE_Z + 0.45), (-0.72, -0.58, PLANE_Z + 1.02), (-0.18, -0.45, PLANE_Z + 1.02)], blue, bevel_depth=0.04))
    component.add(add_curve("Cockpit_CenterFrame", [(-0.68, -0.02, PLANE_Z + 1.11), (-0.49, -0.02, PLANE_Z + 0.45)], blue, bevel_depth=0.035))
    component.add(add_uv_sphere("Cockpit_Highlight", (-0.92, -0.48, PLANE_Z + 0.87), (0.2, 0.035, 0.08), blue_light, segments=28))

    for index, angle in enumerate(range(210, 331, 20), start=1):
        radians = math.radians(angle)
        x_coordinate = -0.54 + math.cos(radians) * 0.74
        y_coordinate = math.sin(radians) * 0.53
        component.add(add_uv_sphere(f"Cockpit_RimFastener_{index}", (x_coordinate, y_coordinate, PLANE_Z + 0.42), (0.028, 0.028, 0.028), metal, segments=18))
    component.joint(
        "HARDPOINT_Cockpit_CanopyBase",
        (-0.54, 0.0, PLANE_Z + 0.41),
        (0.0, 0.0, 1.0),
        joint_type="fixed",
        travel="none",
    )


def build_wings(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    mint = materials["mint"]
    mint_dark = materials["mint_dark"]
    coral = materials["coral"]
    coral_dark = materials["coral_dark"]
    yellow = materials["yellow"]
    ivory = materials["ivory"]
    metal = materials["metal"]

    wing_z = PLANE_Z - 0.08
    # The fixed airfoil ends at the hinge line; control surfaces fill the missing trailing edge.
    near_points = [(-0.94, -0.34), (0.32, -0.4), (0.18, -3.28), (-0.12, -3.45)]
    far_points = [(-0.94, 0.34), (-0.12, 3.45), (0.18, 3.28), (0.32, 0.4)]
    component.add(add_extruded_xy_shape("Wing_Near_MainAirfoil", near_points, wing_z, 0.22, mint, bevel_width=0.15))
    component.add(add_extruded_xy_shape("Wing_Far_MainAirfoil", far_points, wing_z, 0.22, mint, bevel_width=0.15))

    # Root fairings blend the separate wings into the fuselage.
    component.add(add_uv_sphere("Wing_Near_RootFairing", (0.08, -0.58, wing_z), (1.1, 0.34, 0.23), ivory, segments=40))
    component.add(add_uv_sphere("Wing_Far_RootFairing", (0.08, 0.58, wing_z), (1.1, 0.34, 0.23), ivory, segments=40))

    # Separate inner flaps and outer ailerons sit slightly above the main airfoil.
    control_surfaces = [
        ("Wing_Near_Flap", [(0.3, -0.48), (0.86, -0.52), (0.71, -1.72), (0.2, -1.78)], coral, 0.0),
        ("Wing_Near_Aileron", [(0.18, -1.82), (0.7, -1.78), (0.58, -3.08), (0.04, -3.25)], coral_dark, 0.0),
        ("Wing_Far_Flap", [(0.3, 0.48), (0.2, 1.78), (0.71, 1.72), (0.86, 0.52)], coral, 0.0),
        ("Wing_Far_Aileron", [(0.18, 1.82), (0.04, 3.25), (0.58, 3.08), (0.7, 1.78)], coral_dark, 0.0),
    ]
    control_surface_objects: dict[str, bpy.types.Object] = {}
    for name, points, material, z_offset in control_surfaces:
        control_surface_objects[name] = component.add(
            add_extruded_xy_shape(name, points, wing_z + z_offset, 0.14, material, bevel_width=0.055)
        )

    # Hinge rods and panel ribs make the control surfaces read as functional pieces.
    hinge_specs = [
        ("Wing_Near_FlapHinge", "Wing_Near_Flap", (0.29, -0.5, wing_z + 0.1), (0.2, -1.77, wing_z + 0.1), "0..30 deg"),
        ("Wing_Near_AileronHinge", "Wing_Near_Aileron", (0.18, -1.83, wing_z + 0.1), (0.04, -3.2, wing_z + 0.1), "-20..20 deg"),
        ("Wing_Far_FlapHinge", "Wing_Far_Flap", (0.29, 0.5, wing_z + 0.1), (0.2, 1.77, wing_z + 0.1), "0..30 deg"),
        ("Wing_Far_AileronHinge", "Wing_Far_Aileron", (0.18, 1.83, wing_z + 0.1), (0.04, 3.2, wing_z + 0.1), "-20..20 deg"),
    ]
    for name, surface_name, start, end, travel in hinge_specs:
        component.add(add_cylinder_between(name, start, end, 0.026, metal))
        start_vector = Vector((start[0], start[1], wing_z))
        end_vector = Vector((end[0], end[1], wing_z))
        joint = component.joint(
            f"JOINT_{name}",
            tuple((start_vector + end_vector) * 0.5),
            tuple(end_vector - start_vector),
            joint_type="revolute",
            travel=travel,
        )
        parent_keep_world(control_surface_objects[surface_name], joint)

    component.joint(
        "HARDPOINT_WingRoot_Near",
        (0.02, -0.48, wing_z),
        (0.0, 1.0, 0.0),
        joint_type="fixed",
        travel="none",
    )
    component.joint(
        "HARDPOINT_WingRoot_Far",
        (0.02, 0.48, wing_z),
        (0.0, 1.0, 0.0),
        joint_type="fixed",
        travel="none",
    )

    # Leading-edge trim and three chordwise panel breaks per wing.
    component.add(add_curve("Wing_Near_LeadingEdgeTrim", [(-0.91, -0.42, wing_z + 0.12), (-0.55, -1.55, wing_z + 0.14), (-0.16, -3.35, wing_z + 0.12)], yellow, bevel_depth=0.028))
    component.add(add_curve("Wing_Far_LeadingEdgeTrim", [(-0.91, 0.42, wing_z + 0.12), (-0.55, 1.55, wing_z + 0.14), (-0.16, 3.35, wing_z + 0.12)], yellow, bevel_depth=0.028))
    for side_name, sign in (("Near", -1.0), ("Far", 1.0)):
        for index, y_abs in enumerate((0.9, 1.55, 2.3), start=1):
            y_coordinate = sign * y_abs
            component.add(add_curve(f"Wing_{side_name}_PanelLine_{index}", [(-0.69 + y_abs * 0.14, y_coordinate, wing_z + 0.125), (0.3 - y_abs * 0.04, y_coordinate, wing_z + 0.125)], mint_dark, bevel_depth=0.018))

    # Top emblem, raised rivets, and illuminated navigation lamps.
    component.add(add_star("Wing_Near_StarEmblem", (-0.15, -2.35), wing_z + 0.18, 0.34, yellow))
    for side_name, sign in (("Near", -1.0), ("Far", 1.0)):
        for index, y_abs in enumerate((0.62, 0.94, 1.28, 1.66, 2.06, 2.46, 2.82), start=1):
            y_coordinate = sign * y_abs
            x_coordinate = -0.84 + y_abs * 0.2
            component.add(add_uv_sphere(f"Wing_{side_name}_LeadingRivet_{index}", (x_coordinate, y_coordinate, wing_z + 0.145), (0.028, 0.028, 0.018), metal, segments=18))

    component.add(add_uv_sphere("Wing_PortNavLight", (0.24, -3.38, wing_z + 0.07), (0.17, 0.18, 0.12), materials["red_light"], segments=32))
    component.add(add_uv_sphere("Wing_StarboardNavLight", (0.24, 3.38, wing_z + 0.07), (0.17, 0.18, 0.12), materials["green_light"], segments=32))

    # Structural braces read clearly beneath the camera-facing wing.
    component.add(add_cylinder_between("Wing_Near_Strut_Front", (-0.42, -0.48, PLANE_Z - 0.48), (-0.36, -1.72, wing_z - 0.1), 0.042, metal))
    component.add(add_cylinder_between("Wing_Near_Strut_Rear", (0.48, -0.48, PLANE_Z - 0.45), (0.48, -1.62, wing_z - 0.1), 0.042, metal))


def build_tail(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    mint = materials["mint"]
    mint_dark = materials["mint_dark"]
    coral = materials["coral"]
    coral_dark = materials["coral_dark"]
    ivory = materials["ivory"]
    yellow = materials["yellow"]
    metal = materials["metal"]

    tail_z = PLANE_Z + 0.19
    component.add(add_extruded_xy_shape("Tail_Near_Stabilizer", [(1.25, -0.2), (1.74, -0.24), (1.83, -1.55), (1.53, -1.68)], tail_z, 0.16, ivory, bevel_width=0.12))
    component.add(add_extruded_xy_shape("Tail_Far_Stabilizer", [(1.25, 0.2), (1.53, 1.68), (1.83, 1.55), (1.74, 0.24)], tail_z, 0.16, ivory, bevel_width=0.12))
    near_elevator = component.add(add_extruded_xy_shape("Tail_Near_Elevator", [(1.74, -0.27), (2.27, -0.32), (2.13, -1.49), (1.84, -1.55)], tail_z, 0.13, coral, bevel_width=0.055))
    far_elevator = component.add(add_extruded_xy_shape("Tail_Far_Elevator", [(1.74, 0.27), (1.84, 1.55), (2.13, 1.49), (2.27, 0.32)], tail_z, 0.13, coral, bevel_width=0.055))

    fin_points = [(1.28, PLANE_Z + 0.2), (1.91, PLANE_Z + 0.26), (1.85, PLANE_Z + 1.46), (1.56, PLANE_Z + 1.38)]
    component.add(add_extruded_xz_shape("Tail_VerticalFin", fin_points, 0.0, 0.22, mint, bevel_width=0.12))
    rudder_points = [(1.9, PLANE_Z + 0.3), (2.25, PLANE_Z + 0.29), (2.04, PLANE_Z + 1.56), (1.84, PLANE_Z + 1.41)]
    rudder = component.add(add_extruded_xz_shape("Tail_Rudder", rudder_points, 0.0, 0.24, coral_dark, bevel_width=0.06))

    component.add(add_cylinder_between("Tail_Near_ElevatorHinge", (1.74, -0.3, tail_z + 0.1), (1.83, -1.52, tail_z + 0.1), 0.026, metal))
    component.add(add_cylinder_between("Tail_Far_ElevatorHinge", (1.74, 0.3, tail_z + 0.1), (1.83, 1.52, tail_z + 0.1), 0.026, metal))
    near_start = Vector((1.74, -0.3, tail_z))
    near_end = Vector((1.83, -1.52, tail_z))
    near_joint = component.joint(
        "JOINT_Tail_NearElevator",
        tuple((near_start + near_end) * 0.5),
        tuple(near_end - near_start),
        joint_type="revolute",
        travel="-25..25 deg",
    )
    parent_keep_world(near_elevator, near_joint)
    far_start = Vector((1.74, 0.3, tail_z))
    far_end = Vector((1.83, 1.52, tail_z))
    far_joint = component.joint(
        "JOINT_Tail_FarElevator",
        tuple((far_start + far_end) * 0.5),
        tuple(far_end - far_start),
        joint_type="revolute",
        travel="-25..25 deg",
    )
    parent_keep_world(far_elevator, far_joint)
    for index, z_offset in enumerate((0.48, 0.84, 1.2), start=1):
        component.add(add_cylinder(f"Tail_RudderHinge_{index}", (1.89, -0.18, PLANE_Z + z_offset), 0.035, 0.16, metal, rotation=(math.radians(90.0), 0.0, 0.0), vertices=24))
    rudder_joint = component.joint(
        "JOINT_Tail_Rudder",
        (1.89, 0.0, PLANE_Z + 0.9),
        (0.0, 0.0, 1.0),
        joint_type="revolute",
        travel="-30..30 deg",
    )
    parent_keep_world(rudder, rudder_joint)

    component.add(add_curve("Tail_FinTrim", [(1.48, -0.13, PLANE_Z + 0.35), (1.7, -0.13, PLANE_Z + 1.28), (1.98, -0.13, PLANE_Z + 1.53)], yellow, bevel_depth=0.03))
    component.add(add_star_xz("Tail_SideStar", (1.78, PLANE_Z + 1.05), -0.15, 0.16, yellow))
    component.add(add_uv_sphere("Tail_NavigationLight", (2.22, 0.0, PLANE_Z + 1.48), (0.09, 0.09, 0.09), materials["white_light"], segments=28))

    for index, z_offset in enumerate((0.46, 0.68, 0.91, 1.14, 1.35), start=1):
        component.add(add_uv_sphere(f"Tail_FinRivet_{index}", (1.68 + z_offset * 0.09, -0.125, PLANE_Z + z_offset), (0.025, 0.015, 0.025), metal, segments=18))

    component.joint(
        "HARDPOINT_TailplaneRoot",
        (1.62, 0.0, tail_z),
        (0.0, 1.0, 0.0),
        joint_type="fixed",
        travel="none",
    )


def build_propulsion(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    blush = materials["blush"]
    coral = materials["coral"]
    coral_dark = materials["coral_dark"]
    yellow = materials["yellow"]
    metal = materials["metal"]
    steel = materials["steel"]
    navy = materials["navy"]

    component.add(add_uv_sphere("Engine_Cowling", (-2.14, 0.0, PLANE_Z), (0.58, 0.68, 0.61), blush, segments=56))
    component.add(add_torus("Engine_CowlingLip", (-2.54, 0.0, PLANE_Z), 0.56, 0.07, coral_dark, rotation=(0.0, math.radians(90.0), 0.0), scale=(0.96, 1.0, 1.0)))
    propeller_joint = component.joint(
        "JOINT_PropellerShaft",
        (-2.86, 0.0, PLANE_Z),
        (1.0, 0.0, 0.0),
        joint_type="continuous",
        travel="unlimited rotation",
    )
    hub_barrel = component.add(add_cylinder("Engine_HubBarrel", (-2.61, 0.0, PLANE_Z), 0.31, 0.46, metal, rotation=(0.0, math.radians(90.0), 0.0)))
    parent_keep_world(hub_barrel, propeller_joint)

    # Three tapered, rounded blades are individual mesh components.
    blade_points = [(-0.16, 0.22), (0.16, 0.22), (0.2, 0.78), (0.14, 1.12), (-0.13, 1.12), (-0.23, 1.02)]
    blade_tip_points = [(-0.13, 1.05), (0.14, 1.05), (0.1, 1.2), (-0.08, 1.31), (-0.2, 1.11)]
    for index, angle in enumerate((0.0, math.radians(120.0), math.radians(240.0)), start=1):
        blade = component.add(add_local_yz_prism(f"Propeller_Blade_{index}", blade_points, 0.16, (-2.86, 0.0, PLANE_Z), coral, rotation_x=angle, bevel_width=0.065))
        blade_tip = component.add(add_local_yz_prism(f"Propeller_Tip_{index}", blade_tip_points, 0.17, (-2.86, 0.0, PLANE_Z), yellow, rotation_x=angle, bevel_width=0.05))
        parent_keep_world(blade, propeller_joint)
        parent_keep_world(blade_tip, propeller_joint)

    spinner = component.add(add_uv_sphere("Propeller_Spinner", (-3.02, 0.0, PLANE_Z), (0.34, 0.34, 0.34), yellow, segments=48))
    spinner_ring = component.add(add_torus("Propeller_SpinnerRing", (-2.85, 0.0, PLANE_Z), 0.28, 0.026, steel, rotation=(0.0, math.radians(90.0), 0.0)))
    parent_keep_world(spinner, propeller_joint)
    parent_keep_world(spinner_ring, propeller_joint)

    for index, angle in enumerate(range(0, 360, 60), start=1):
        radians = math.radians(angle)
        bolt = component.add(add_uv_sphere(f"Engine_HubBolt_{index}", (-2.88, math.cos(radians) * 0.23, PLANE_Z + math.sin(radians) * 0.23), (0.04, 0.04, 0.04), steel, segments=20))
        parent_keep_world(bolt, propeller_joint)

    # Stacked exhaust tubes and cowling vent slats add mechanical scale.
    for index, x_coordinate in enumerate((-2.0, -1.74), start=1):
        component.add(add_cylinder(f"Engine_Exhaust_{index}", (x_coordinate, -0.66, PLANE_Z - 0.38), 0.065, 0.3, steel, rotation=(0.0, math.radians(90.0), 0.0), vertices=28))
        component.add(add_cylinder(f"Engine_ExhaustOpening_{index}", (x_coordinate - 0.16, -0.66, PLANE_Z - 0.38), 0.048, 0.012, navy, rotation=(0.0, math.radians(90.0), 0.0), vertices=28))
    for index, z_offset in enumerate((-0.22, 0.0, 0.22), start=1):
        component.add(add_beveled_cube(f"Engine_CowlingSlat_{index}", (-2.19, -0.675, PLANE_Z + z_offset), (0.24, 0.04, 0.055), navy, bevel=0.022))


def add_wheel(
    component: Component,
    prefix: str,
    location: tuple[float, float, float],
    radius: float,
    materials: dict[str, bpy.types.Material],
    *,
    visible_face_y: float,
) -> list[bpy.types.Object]:
    tire = materials["tire"]
    steel = materials["steel"]
    yellow = materials["yellow"]
    coral = materials["coral"]
    parts: list[bpy.types.Object] = []

    parts.append(component.add(add_torus(f"{prefix}_Tire", location, radius * 0.7, radius * 0.3, tire, rotation=(math.radians(90.0), 0.0, 0.0))))
    parts.append(component.add(add_cylinder(f"{prefix}_Rim", location, radius * 0.48, 0.18, steel, rotation=(math.radians(90.0), 0.0, 0.0), vertices=48)))
    parts.append(component.add(add_cylinder(f"{prefix}_HubCap", (location[0], visible_face_y, location[2]), radius * 0.23, 0.035, yellow, rotation=(math.radians(90.0), 0.0, 0.0), vertices=32)))

    # Two raised tread channels and five hub bolts.
    parts.append(component.add(add_torus(f"{prefix}_TreadOuter", location, radius * 0.82, 0.017, materials["navy"], rotation=(math.radians(90.0), 0.0, 0.0))))
    parts.append(component.add(add_torus(f"{prefix}_TreadInner", location, radius * 0.58, 0.014, materials["navy"], rotation=(math.radians(90.0), 0.0, 0.0))))
    for index, angle in enumerate(range(0, 360, 72), start=1):
        radians = math.radians(angle)
        parts.append(component.add(add_uv_sphere(f"{prefix}_HubBolt_{index}", (location[0] + math.cos(radians) * radius * 0.31, visible_face_y - 0.02, location[2] + math.sin(radians) * radius * 0.31), (0.025, 0.014, 0.025), coral, segments=18)))
    return parts


def build_landing_gear(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    metal = materials["metal"]
    steel = materials["steel"]
    coral = materials["coral"]

    # Main gear pair.
    for side_name, y_coordinate in (("Near", -0.76), ("Far", 0.76)):
        wheel_location = (0.45, y_coordinate, MAIN_WHEEL_Z)
        visible_face = y_coordinate - 0.12 if y_coordinate < 0 else y_coordinate + 0.12
        wheel_parts = add_wheel(component, f"Gear_Main{side_name}", wheel_location, MAIN_WHEEL_RADIUS, materials, visible_face_y=visible_face)
        axle_joint = component.joint(
            f"JOINT_Gear_Main{side_name}_Axle",
            wheel_location,
            (0.0, 1.0, 0.0),
            joint_type="continuous",
            travel="unlimited wheel rotation",
        )
        for wheel_part in wheel_parts:
            parent_keep_world(wheel_part, axle_joint)
        upper_hardpoint = (0.22, y_coordinate * 0.68, PLANE_Z - 0.47)
        component.joint(
            f"HARDPOINT_Gear_Main{side_name}_Upper",
            upper_hardpoint,
            (0.0, 1.0, 0.0),
            joint_type="fixed",
            travel="none",
        )
        component.joint(
            f"CONTACT_Gear_Main{side_name}",
            (wheel_location[0], wheel_location[1], PLATFORM_TOP_Z),
            (0.0, 0.0, 1.0),
            joint_type="contact",
            travel="platform datum",
        )
        component.add(add_cylinder_between(f"Gear_Main{side_name}_Shock", (0.22, y_coordinate * 0.68, PLANE_Z - 0.47), (0.42, y_coordinate, 0.32), 0.065, metal))
        component.add(add_cylinder_between(f"Gear_Main{side_name}_ForkFront", (0.42, y_coordinate - 0.06, 0.32), (0.24, y_coordinate - 0.06, MAIN_WHEEL_Z), 0.042, steel))
        component.add(add_cylinder_between(f"Gear_Main{side_name}_ForkRear", (0.42, y_coordinate + 0.06, 0.32), (0.66, y_coordinate + 0.06, MAIN_WHEEL_Z), 0.042, steel))
        component.add(add_uv_sphere(f"Gear_Main{side_name}_Joint", (0.42, y_coordinate, 0.32), (0.11, 0.11, 0.11), coral, segments=28))
        component.add(add_uv_sphere(f"Gear_Main{side_name}_Fairing", (0.29, y_coordinate * 0.72, PLANE_Z - 0.55), (0.22, 0.16, 0.29), coral, segments=36))

    # Steerable nose wheel and its fork.
    nose_location = (-1.35, -0.08, NOSE_WHEEL_Z)
    nose_wheel_parts = add_wheel(component, "Gear_Nose", nose_location, NOSE_WHEEL_RADIUS, materials, visible_face_y=-0.2)
    nose_axle_joint = component.joint(
        "JOINT_Gear_Nose_Axle",
        nose_location,
        (0.0, 1.0, 0.0),
        joint_type="continuous",
        travel="unlimited wheel rotation",
    )
    for wheel_part in nose_wheel_parts:
        parent_keep_world(wheel_part, nose_axle_joint)
    component.joint(
        "HARDPOINT_Gear_Nose_Steering",
        (-1.12, -0.02, PLANE_Z - 0.52),
        (0.0, 0.0, 1.0),
        joint_type="revolute",
        travel="-35..35 deg",
    )
    component.joint(
        "CONTACT_Gear_Nose",
        (nose_location[0], nose_location[1], PLATFORM_TOP_Z),
        (0.0, 0.0, 1.0),
        joint_type="contact",
        travel="platform datum",
    )
    component.add(add_cylinder_between("Gear_Nose_Shock", (-1.12, -0.02, PLANE_Z - 0.52), (-1.31, -0.05, 0.29), 0.055, metal))
    component.add(add_cylinder_between("Gear_Nose_ForkNear", (-1.31, -0.14, 0.29), (-1.35, -0.14, NOSE_WHEEL_Z), 0.037, steel))
    component.add(add_cylinder_between("Gear_Nose_ForkFar", (-1.31, 0.02, 0.29), (-1.35, 0.02, NOSE_WHEEL_Z), 0.037, steel))
    component.add(add_cylinder("Gear_Nose_Axle", nose_location, 0.04, 0.34, steel, rotation=(math.radians(90.0), 0.0, 0.0), vertices=28))
    component.add(add_uv_sphere("Gear_Nose_Joint", (-1.31, -0.06, 0.29), (0.09, 0.09, 0.09), coral, segments=28))

    # Brake hose is a distinct curve running down the visible main strut.
    component.add(add_curve("Gear_Near_BrakeHose", [(0.16, -0.55, PLANE_Z - 0.48), (0.27, -0.78, 0.55), (0.32, -0.84, 0.15)], materials["navy"], bevel_depth=0.022))


def build_face_and_trim(component: Component, materials: dict[str, bpy.types.Material]) -> None:
    white = materials["white"]
    blue = materials["blue"]
    blue_light = materials["blue_light"]
    navy = materials["navy"]
    coral = materials["coral"]
    blush = materials["blush"]

    eye_specs = [(-1.68, -0.57), (-1.12, -0.7)]
    for index, (x_coordinate, y_coordinate) in enumerate(eye_specs, start=1):
        component.add(add_uv_sphere(f"Face_EyeWhite_{index}", (x_coordinate, y_coordinate, PLANE_Z + 0.12), (0.205, 0.06, 0.265), white, segments=40))
        component.add(add_uv_sphere(f"Face_Iris_{index}", (x_coordinate - 0.02, y_coordinate - 0.058, PLANE_Z + 0.115), (0.13, 0.038, 0.175), blue, segments=36))
        component.add(add_uv_sphere(f"Face_Pupil_{index}", (x_coordinate - 0.04, y_coordinate - 0.09, PLANE_Z + 0.11), (0.072, 0.024, 0.11), navy, segments=32))
        component.add(add_uv_sphere(f"Face_EyeSparkleLarge_{index}", (x_coordinate - 0.073, y_coordinate - 0.109, PLANE_Z + 0.19), (0.035, 0.012, 0.047), white, segments=20))
        component.add(add_uv_sphere(f"Face_EyeSparkleSmall_{index}", (x_coordinate + 0.005, y_coordinate - 0.108, PLANE_Z + 0.105), (0.018, 0.01, 0.024), blue_light, segments=18))

    component.add(add_curve("Face_LeftBrow", [(-1.88, -0.565, PLANE_Z + 0.38), (-1.7, -0.59, PLANE_Z + 0.43), (-1.52, -0.62, PLANE_Z + 0.39)], navy, bevel_depth=0.035))
    component.add(add_curve("Face_RightBrow", [(-1.3, -0.69, PLANE_Z + 0.39), (-1.12, -0.72, PLANE_Z + 0.43), (-0.94, -0.73, PLANE_Z + 0.37)], navy, bevel_depth=0.035))
    component.add(add_uv_sphere("Face_CheekFront", (-1.98, -0.47, PLANE_Z - 0.13), (0.16, 0.035, 0.095), blush, segments=30))
    component.add(add_uv_sphere("Face_CheekRear", (-0.86, -0.73, PLANE_Z - 0.13), (0.16, 0.035, 0.095), blush, segments=30))

    component.add(add_curve("Face_Smile", [(-1.68, -0.67, PLANE_Z - 0.14), (-1.43, -0.75, PLANE_Z - 0.31), (-1.16, -0.76, PLANE_Z - 0.14)], navy, bevel_depth=0.05))
    component.add(add_uv_sphere("Face_Tongue", (-1.42, -0.765, PLANE_Z - 0.265), (0.11, 0.027, 0.055), coral, segments=28))


def build_presentation(
    materials: dict[str, bpy.types.Material],
    scene_collection: bpy.types.Collection,
) -> None:
    presentation = new_collection("90_PRESENTATION", scene_collection)

    def add(obj: bpy.types.Object) -> bpy.types.Object:
        move_to_collection(obj, presentation)
        return obj

    add(add_cylinder("Presentation_Platform", (0.0, 0.0, -0.64), 4.65, 0.64, materials["platform"], vertices=96))
    add(add_cylinder("Presentation_TrimUpper", (0.0, 0.0, -0.38), 4.68, 0.09, materials["platform_trim"], vertices=96))
    add(add_cylinder("Presentation_TrimLower", (0.0, 0.0, -0.92), 4.7, 0.11, materials["platform_trim"], vertices=96))

    # Background clouds are deliberately sparse so the mechanical details remain readable.
    cloud_specs = [
        ("Presentation_Cloud_BackLeft", (-2.9, 2.2, 0.35), 0.62),
        ("Presentation_Cloud_BackRight", (2.65, 2.75, 0.58), 0.58),
        ("Presentation_Cloud_FrontRight", (3.05, -2.75, -0.08), 0.52),
    ]
    for name, location, scale in cloud_specs:
        root = add_cloud(name, location, scale, materials["cloud"])
        add(root)
        for child in root.children:
            move_to_collection(child, presentation)

    # Decorative raised stars and dots are separate editable pieces.
    add(add_star("Presentation_Star_Left", (-3.48, -0.48), -0.285, 0.22, materials["yellow"]))
    add(add_star("Presentation_Star_Right", (3.54, 0.72), -0.285, 0.18, materials["coral"]))
    for index, (location, material) in enumerate(
        [((-2.25, -3.3, -0.25), materials["mint"]), ((2.55, -3.12, -0.25), materials["yellow"]), ((3.5, -1.4, -0.25), materials["coral"])],
        start=1,
    ):
        add(add_uv_sphere(f"Presentation_CandyDot_{index}", location, (0.12, 0.12, 0.12), material, segments=28))


def configure_scene(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(RENDER_PATH)
    scene.render.film_transparent = False

    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.05
    scene.view_settings.gamma = 1.0
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("Detailed Pastel Sky")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = hex_color("AFCDE7")
    background.inputs["Strength"].default_value = 0.38

    bpy.ops.object.camera_add(location=(-8.7, -10.6, 6.9))
    camera = bpy.context.object
    camera.name = "Presentation_Camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 7.75
    camera.data.lens = 55
    point_at(camera, (-0.05, 0.0, 1.0))
    scene.camera = camera

    def add_area(
        name: str,
        location: tuple[float, float, float],
        energy: float,
        size: float,
        color: str,
    ) -> None:
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light_data.color = hex_color(color)[:3]
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        bpy.context.collection.objects.link(light)
        point_at(light, (0.0, 0.0, 1.0))

    add_area("Lighting_Key", (-5.2, -6.5, 10.0), 1050.0, 5.2, "FFF0D1")
    add_area("Lighting_Fill", (6.2, -2.6, 6.3), 620.0, 4.8, "C7E8FF")
    add_area("Lighting_Rim", (2.5, 6.0, 8.5), 820.0, 4.2, "FFD1D8")

    sun_data = bpy.data.lights.new(name="Lighting_Sun", type="SUN")
    sun_data.energy = 0.7
    sun_data.angle = math.radians(20.0)
    sun = bpy.data.objects.new("Lighting_Sun", sun_data)
    sun.rotation_euler = (math.radians(30.0), math.radians(-18.0), math.radians(-30.0))
    bpy.context.collection.objects.link(sun)


def validate_assembly() -> None:
    tolerance = 1e-5
    checks = {
        "main gear contact datum": abs((MAIN_WHEEL_Z - MAIN_WHEEL_RADIUS) - PLATFORM_TOP_Z),
        "nose gear contact datum": abs((NOSE_WHEEL_Z - NOSE_WHEEL_RADIUS) - PLATFORM_TOP_Z),
        "propeller shaft centerline Y": abs(bpy.data.objects["JOINT_PropellerShaft"].location.y),
        "propeller shaft centerline Z": abs(bpy.data.objects["JOINT_PropellerShaft"].location.z - PLANE_Z),
    }
    failed = [name for name, error in checks.items() if error > tolerance]
    if failed:
        raise RuntimeError(f"Assembly datum validation failed: {', '.join(failed)}")

    required_joint_parents = {
        "Wing_Near_Flap": "JOINT_Wing_Near_FlapHinge",
        "Wing_Near_Aileron": "JOINT_Wing_Near_AileronHinge",
        "Wing_Far_Flap": "JOINT_Wing_Far_FlapHinge",
        "Wing_Far_Aileron": "JOINT_Wing_Far_AileronHinge",
        "Tail_Near_Elevator": "JOINT_Tail_NearElevator",
        "Tail_Far_Elevator": "JOINT_Tail_FarElevator",
        "Tail_Rudder": "JOINT_Tail_Rudder",
        "Propeller_Blade_1": "JOINT_PropellerShaft",
        "Gear_MainNear_Tire": "JOINT_Gear_MainNear_Axle",
        "Gear_MainFar_Tire": "JOINT_Gear_MainFar_Axle",
        "Gear_Nose_Tire": "JOINT_Gear_Nose_Axle",
    }
    for child_name, parent_name in required_joint_parents.items():
        child = bpy.data.objects.get(child_name)
        if child is None or child.parent is None or child.parent.name != parent_name:
            raise RuntimeError(f"Joint parenting validation failed: {child_name} -> {parent_name}")


def create_detailed_airplane() -> None:
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene)
    materials = build_materials()

    aircraft_collection = new_collection("AIRCRAFT_V2_MODULAR", scene.collection)
    aircraft_root = bpy.data.objects.new("AIRPLANE_ROOT", None)
    aircraft_root.empty_display_type = "ARROWS"
    aircraft_root.empty_display_size = 0.55
    aircraft_collection.objects.link(aircraft_root)

    components = {
        "fuselage": Component("01_FUSELAGE", aircraft_collection, aircraft_root),
        "cockpit": Component("02_COCKPIT_INTERIOR", aircraft_collection, aircraft_root),
        "wings": Component("03_WINGS_CONTROLS", aircraft_collection, aircraft_root),
        "tail": Component("04_TAIL_CONTROLS", aircraft_collection, aircraft_root),
        "propulsion": Component("05_PROPULSION", aircraft_collection, aircraft_root),
        "gear": Component("06_LANDING_GEAR", aircraft_collection, aircraft_root),
        "face": Component("07_FACE_TRIM", aircraft_collection, aircraft_root),
    }

    build_fuselage(components["fuselage"], materials)
    build_cockpit(components["cockpit"], materials)
    build_wings(components["wings"], materials)
    build_tail(components["tail"], materials)
    build_propulsion(components["propulsion"], materials)
    build_landing_gear(components["gear"], materials)
    build_face_and_trim(components["face"], materials)
    build_presentation(materials, scene.collection)
    validate_assembly()

    # Metadata documents the assembly hierarchy inside the deliverable.
    scene["artwork_title"] = "Cloudberry Air — Detailed Modular Toy Plane"
    scene["assembly_root"] = "AIRPLANE_ROOT"
    scene["component_collections"] = ", ".join(component.collection.name for component in components.values())
    scene["modeling_note"] = "Each major aircraft subsystem is isolated in its own collection and parented through an assembly empty."
    scene["joint_standard"] = "Local Z is the motion axis on every JOINT_* empty; travel metadata is stored as a custom property."
    scene["contact_datum_z"] = PLATFORM_TOP_Z

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    create_detailed_airplane()

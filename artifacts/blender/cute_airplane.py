from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


OUTPUT_DIR = Path(__file__).resolve().parent
BLEND_PATH = OUTPUT_DIR / "cute_airplane.blend"
RENDER_PATH = OUTPUT_DIR / "cute_airplane.png"


def hex_color(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    srgb = tuple(int(value[index:index + 2], 16) / 255.0 for index in (0, 2, 4))

    def to_linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    return tuple(to_linear(channel) for channel in srgb) + (1.0,)


def make_material(
    name: str,
    color: str,
    *,
    roughness: float = 0.42,
    metallic: float = 0.0,
    coat: float = 0.18,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = hex_color(color)

    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = hex_color(color)
        principled.inputs["Roughness"].default_value = roughness
        principled.inputs["Metallic"].default_value = metallic
        coat_input = principled.inputs.get("Coat Weight")
        if coat_input is not None:
            coat_input.default_value = coat
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.append(material)


def smooth(obj: bpy.types.Object) -> None:
    if hasattr(obj.data, "polygons"):
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def add_uv_sphere(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
    *,
    segments: int = 48,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=max(16, segments // 2),
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign_material(obj, material)
    smooth(obj)
    return obj


def add_beveled_cube(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    *,
    bevel: float = 0.12,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    modifier = obj.modifiers.new(name="Soft edges", type="BEVEL")
    modifier.width = bevel
    modifier.segments = 5
    modifier.limit_method = "ANGLE"
    assign_material(obj, material)
    smooth(obj)
    return obj


def add_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    material: bpy.types.Material,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    vertices: int = 48,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    smooth(obj)
    bevel = obj.modifiers.new(name="Soft rim", type="BEVEL")
    bevel.width = min(radius, depth) * 0.18
    bevel.segments = 4
    return obj


def add_cylinder_between(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    start_vec = Vector(start)
    end_vec = Vector(end)
    direction = end_vec - start_vec
    midpoint = (start_vec + end_vec) * 0.5
    obj = add_cylinder(name, tuple(midpoint), radius, direction.length, material, vertices=32)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return obj


def add_extruded_xy_shape(
    name: str,
    points: list[tuple[float, float]],
    z: float,
    thickness: float,
    material: bpy.types.Material,
    *,
    bevel_width: float = 0.12,
) -> bpy.types.Object:
    half = thickness * 0.5
    vertices = [(x, y, z + half) for x, y in points]
    vertices.extend((x, y, z - half) for x, y in points)
    count = len(points)

    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, next_index + count, index + count))

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)

    bevel = obj.modifiers.new(name="Rounded outline", type="BEVEL")
    bevel.width = bevel_width
    bevel.segments = 5
    bevel.limit_method = "ANGLE"
    smooth(obj)
    return obj


def add_extruded_xz_shape(
    name: str,
    points: list[tuple[float, float]],
    y: float,
    thickness: float,
    material: bpy.types.Material,
    *,
    bevel_width: float = 0.1,
) -> bpy.types.Object:
    half = thickness * 0.5
    vertices = [(x, y - half, z) for x, z in points]
    vertices.extend((x, y + half, z) for x, z in points)
    count = len(points)

    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, next_index + count, index + count))

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)

    bevel = obj.modifiers.new(name="Rounded outline", type="BEVEL")
    bevel.width = bevel_width
    bevel.segments = 5
    bevel.limit_method = "ANGLE"
    smooth(obj)
    return obj


def add_curve(
    name: str,
    points: list[tuple[float, float, float]],
    material: bpy.types.Material,
    *,
    bevel_depth: float = 0.04,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name=f"{name}Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 5
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bezier_point, coordinate in zip(spline.bezier_points, points, strict=True):
        bezier_point.co = coordinate
        bezier_point.handle_left_type = "AUTO"
        bezier_point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)
    return obj


def add_cloud(
    name: str,
    location: tuple[float, float, float],
    scale: float,
    material: bpy.types.Material,
) -> bpy.types.Empty:
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.location = location
    bpy.context.collection.objects.link(root)

    puffs = [
        ((-0.72, 0.0, 0.0), (0.72, 0.55, 0.5)),
        ((-0.18, 0.0, 0.18), (0.82, 0.68, 0.68)),
        ((0.42, 0.0, 0.08), (0.72, 0.56, 0.55)),
        ((0.82, 0.0, -0.03), (0.52, 0.42, 0.4)),
        ((0.12, 0.0, -0.12), (1.05, 0.5, 0.42)),
    ]
    for index, (offset, puff_scale) in enumerate(puffs):
        puff = add_uv_sphere(
            f"{name}_Puff_{index + 1}",
            (
                location[0] + offset[0] * scale,
                location[1] + offset[1] * scale,
                location[2] + offset[2] * scale,
            ),
            tuple(component * scale for component in puff_scale),
            material,
            segments=32,
        )
        puff.parent = root
    return root


def point_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.filepath = str(RENDER_PATH)
    scene.render.image_settings.color_depth = "8"

    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    world = bpy.data.worlds.new("Pastel Sky") if bpy.data.worlds.get("World") is None else bpy.data.worlds["World"]
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = hex_color("BFDDF8")
    background.inputs["Strength"].default_value = 0.42

    ivory = make_material("Warm Ivory", "FFF4D8", roughness=0.38, coat=0.28)
    mint = make_material("Mint Wings", "70D7C7", roughness=0.35, coat=0.3)
    coral = make_material("Coral Accents", "FF8295", roughness=0.34, coat=0.25)
    yellow = make_material("Sunny Yellow", "FFD166", roughness=0.32, coat=0.3)
    blue = make_material("Window Blue", "4F9FB4", roughness=0.2, metallic=0.05, coat=0.5)
    pale_blue = make_material("Window Highlight", "A8E5EF", roughness=0.25, coat=0.35)
    navy = make_material("Soft Navy", "243B53", roughness=0.3, coat=0.2)
    blush = make_material("Blush", "FFB0BB", roughness=0.42, coat=0.15)
    cloud_white = make_material("Cloud White", "FFFDF8", roughness=0.7, coat=0.05)
    lavender = make_material("Lavender Platform", "B8ACEA", roughness=0.55, coat=0.08)
    platform_trim = make_material("Platform Trim", "8C80CA", roughness=0.45, coat=0.12)
    strut_metal = make_material("Warm Metal", "D9B36C", roughness=0.28, metallic=0.48, coat=0.25)

    plane_z = 1.42

    # Fuselage and tail cone.
    add_uv_sphere("Fuselage", (0.0, 0.0, plane_z), (2.48, 0.78, 0.72), ivory)
    add_uv_sphere("Tail Cone", (1.92, 0.0, plane_z + 0.04), (0.75, 0.44, 0.4), ivory)
    add_uv_sphere("Nose Blush", (-2.18, -0.15, plane_z - 0.04), (0.48, 0.66, 0.56), blush)

    # Main wings and their candy-colored tips.
    add_extruded_xy_shape(
        "Near Wing",
        [(-0.9, -0.34), (0.86, -0.4), (0.58, -3.18), (-0.08, -3.42)],
        plane_z - 0.08,
        0.18,
        mint,
        bevel_width=0.15,
    )
    add_extruded_xy_shape(
        "Far Wing",
        [(-0.9, 0.34), (-0.08, 3.42), (0.58, 3.18), (0.86, 0.4)],
        plane_z - 0.08,
        0.18,
        mint,
        bevel_width=0.15,
    )
    add_uv_sphere("Near Wing Tip", (0.24, -3.22, plane_z - 0.06), (0.43, 0.34, 0.13), coral)
    add_uv_sphere("Far Wing Tip", (0.24, 3.22, plane_z - 0.06), (0.43, 0.34, 0.13), coral)

    # Tail planes and upright fin.
    add_extruded_xy_shape(
        "Near Tail Wing",
        [(1.27, -0.2), (2.27, -0.25), (2.12, -1.52), (1.55, -1.66)],
        plane_z + 0.18,
        0.14,
        coral,
        bevel_width=0.11,
    )
    add_extruded_xy_shape(
        "Far Tail Wing",
        [(1.27, 0.2), (1.55, 1.66), (2.12, 1.52), (2.27, 0.25)],
        plane_z + 0.18,
        0.14,
        coral,
        bevel_width=0.11,
    )
    add_extruded_xz_shape(
        "Tail Fin",
        [
            (1.28, plane_z + 0.2),
            (2.25, plane_z + 0.22),
            (2.05, plane_z + 1.55),
            (1.58, plane_z + 1.32),
        ],
        0.0,
        0.2,
        coral,
        bevel_width=0.12,
    )
    add_uv_sphere("Tail Fin Dot", (1.87, -0.115, plane_z + 1.05), (0.18, 0.055, 0.18), yellow)

    # Cockpit and passenger windows.
    add_uv_sphere("Cockpit", (-0.68, 0.0, plane_z + 0.62), (0.76, 0.59, 0.42), blue)
    add_uv_sphere("Cockpit Glint", (-1.02, -0.43, plane_z + 0.8), (0.18, 0.045, 0.09), pale_blue)
    for index, x_coordinate in enumerate((0.24, 0.82, 1.36), start=1):
        surface_y = -0.78 * math.sqrt(max(0.0, 1.0 - (x_coordinate / 2.48) ** 2))
        add_uv_sphere(
            f"Window Rim {index}",
            (x_coordinate, surface_y - 0.025, plane_z + 0.13),
            (0.245, 0.06, 0.245),
            cloud_white,
            segments=32,
        )
        add_uv_sphere(
            f"Window {index}",
            (x_coordinate, surface_y - 0.078, plane_z + 0.13),
            (0.19, 0.045, 0.19),
            blue,
            segments=32,
        )
        add_uv_sphere(
            f"Window Glint {index}",
            (x_coordinate - 0.055, surface_y - 0.12, plane_z + 0.19),
            (0.055, 0.018, 0.045),
            pale_blue,
            segments=24,
        )

    # Friendly face on the camera-facing side of the nose.
    eye_specs = [(-1.72, -0.565), (-1.17, -0.7)]
    for index, (x_coordinate, y_coordinate) in enumerate(eye_specs, start=1):
        add_uv_sphere(
            f"Eye White {index}",
            (x_coordinate, y_coordinate, plane_z + 0.13),
            (0.19, 0.06, 0.24),
            cloud_white,
            segments=32,
        )
        add_uv_sphere(
            f"Pupil {index}",
            (x_coordinate - 0.025, y_coordinate - 0.055, plane_z + 0.115),
            (0.095, 0.035, 0.135),
            navy,
            segments=32,
        )
        add_uv_sphere(
            f"Eye Sparkle {index}",
            (x_coordinate - 0.055, y_coordinate - 0.088, plane_z + 0.18),
            (0.028, 0.012, 0.038),
            cloud_white,
            segments=20,
        )

    add_uv_sphere("Near Cheek", (-1.98, -0.47, plane_z - 0.1), (0.14, 0.035, 0.085), coral, segments=28)
    add_uv_sphere("Far Cheek", (-0.94, -0.73, plane_z - 0.1), (0.14, 0.035, 0.085), coral, segments=28)
    add_curve(
        "Smile",
        [
            (-1.7, -0.66, plane_z - 0.13),
            (-1.45, -0.73, plane_z - 0.28),
            (-1.18, -0.75, plane_z - 0.13),
        ],
        navy,
        bevel_depth=0.043,
    )

    # Propeller, hub and spinner.
    add_cylinder(
        "Propeller Hub",
        (-2.48, 0.0, plane_z),
        0.31,
        0.44,
        strut_metal,
        rotation=(0.0, math.radians(90.0), 0.0),
    )
    for index, angle in enumerate((0.0, math.radians(120.0), math.radians(240.0)), start=1):
        radius = 0.68
        y_coordinate = -math.sin(angle) * radius
        z_coordinate = plane_z + math.cos(angle) * radius
        add_beveled_cube(
            f"Propeller Blade {index}",
            (-2.76, y_coordinate, z_coordinate),
            (0.14, 0.3, 1.18),
            coral,
            bevel=0.13,
            rotation=(angle, 0.0, 0.0),
        )
    add_uv_sphere("Spinner", (-2.88, 0.0, plane_z), (0.3, 0.31, 0.31), yellow)

    # Tiny landing gear gives the model a toy-like silhouette.
    gear_data = [
        ("Front", -0.82, -0.61),
        ("Rear", 0.92, -0.67),
    ]
    for label, x_coordinate, y_coordinate in gear_data:
        add_cylinder_between(
            f"{label} Gear Strut",
            (x_coordinate, y_coordinate + 0.08, plane_z - 0.53),
            (x_coordinate, y_coordinate, plane_z - 0.92),
            0.055,
            strut_metal,
        )
        add_cylinder(
            f"{label} Wheel",
            (x_coordinate, y_coordinate, plane_z - 0.94),
            0.25,
            0.2,
            navy,
            rotation=(math.radians(90.0), 0.0, 0.0),
        )
        add_cylinder(
            f"{label} Wheel Hub",
            (x_coordinate, y_coordinate - 0.115, plane_z - 0.94),
            0.09,
            0.035,
            yellow,
            rotation=(math.radians(90.0), 0.0, 0.0),
            vertices=32,
        )

    # Floating diorama base.
    add_cylinder("Display Island", (0.0, 0.0, -0.72), 5.1, 0.42, lavender, vertices=96)
    add_cylinder("Display Island Trim", (0.0, 0.0, -0.91), 5.14, 0.08, platform_trim, vertices=96)

    add_cloud("Cloud A", (-3.0, 2.15, 0.2), 0.76, cloud_white)
    add_cloud("Cloud B", (2.7, 2.55, 0.42), 0.7, cloud_white)
    add_cloud("Cloud C", (2.92, -2.55, -0.02), 0.78, cloud_white)

    # A few soft candy dots make the base feel like a playful sky island.
    for index, (location, radius, material) in enumerate(
        [
            ((-3.7, -0.1, -0.42), 0.15, yellow),
            ((3.52, 0.42, -0.42), 0.12, coral),
            ((1.88, 3.42, -0.42), 0.11, yellow),
            ((-1.75, -3.62, -0.42), 0.13, mint),
        ],
        start=1,
    ):
        add_uv_sphere(f"Candy Dot {index}", location, (radius, radius, radius), material, segments=28)

    # Camera and soft three-point lighting.
    bpy.ops.object.camera_add(location=(-8.6, -10.8, 7.4))
    camera = bpy.context.object
    camera.name = "Camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.1
    camera.data.lens = 52
    point_at(camera, (0.0, 0.0, 0.85))
    scene.camera = camera

    def add_area_light(
        name: str,
        location: tuple[float, float, float],
        energy: float,
        size: float,
        color: str,
        target: tuple[float, float, float] = (0.0, 0.0, 1.0),
    ) -> None:
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light_data.color = hex_color(color)[:3]
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        bpy.context.collection.objects.link(light)
        point_at(light, target)

    add_area_light("Key Light", (-4.8, -6.8, 10.5), 950.0, 5.5, "FFF2D0")
    add_area_light("Fill Light", (6.5, -2.0, 6.2), 620.0, 5.0, "C8E8FF")
    add_area_light("Rim Light", (2.6, 6.4, 8.5), 780.0, 4.5, "FFD2D8")

    sun_data = bpy.data.lights.new(name="Soft Sun", type="SUN")
    sun_data.energy = 0.8
    sun_data.angle = math.radians(18.0)
    sun = bpy.data.objects.new("Soft Sun", sun_data)
    sun.rotation_euler = (math.radians(28.0), math.radians(-18.0), math.radians(-32.0))
    bpy.context.collection.objects.link(sun)

    # Organize the Outliner with a friendly scene label.
    scene["artwork_title"] = "Cloudberry Air — Cute Toy Airplane"
    scene["artwork_notes"] = "Editable procedural scene generated for a pastel 3D airplane render."

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    create_scene()

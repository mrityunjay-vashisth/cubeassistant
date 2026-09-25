from __future__ import annotations

import json
from pathlib import Path

import bmesh
import bpy


SCRIPT_DIR = Path(__file__).resolve().parent
BLEND_PATH = SCRIPT_DIR / "cute_cartoon_trainer_v4.blend"
RENDER_PATHS = [
    SCRIPT_DIR / "cute_cartoon_trainer_v4.png",
    SCRIPT_DIR / "cute_cartoon_trainer_v4_detail.png",
    SCRIPT_DIR / "cute_cartoon_trainer_v4_side.png",
    SCRIPT_DIR / "cute_cartoon_trainer_v4_front.png",
    SCRIPT_DIR / "cute_cartoon_trainer_v4_top.png",
]

PRIMARY_CLOSED_MESHES = [
    "V4_Continuous_Fuselage_Shell",
    "V4_Continuous_Parent_Wing",
    "V4_Wing_Carrythrough_Saddle_Fairing",
    "V4_Continuous_Horizontal_Tail",
    "V4_Continuous_Vertical_Tail",
    "V4_Dorsal_Tail_Fillet",
]

REQUIRED_JOINTS = [
    "DATUM_DESIGN_CG",
    "DATUM_WING_QUARTER_CHORD",
    "JNT_PROPELLER_AXIS",
    "JNT_NOSE_STEERING",
    "JNT_RIGHT_FLAP_HINGE",
    "JNT_LEFT_FLAP_HINGE",
    "JNT_RIGHT_AILERON_HINGE",
    "JNT_LEFT_AILERON_HINGE",
    "JNT_RIGHT_ELEVATOR_HINGE",
    "JNT_LEFT_ELEVATOR_HINGE",
    "JNT_RUDDER_HINGE",
]


def non_manifold_edge_count(obj: bpy.types.Object) -> int:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = sum(1 for edge in bm.edges if not edge.is_manifold)
    bm.free()
    return count


def main() -> None:
    bpy.ops.wm.open_mainfile(filepath=str(BLEND_PATH))
    errors: list[str] = []
    root = bpy.data.objects.get("V4_AIRCRAFT_MASTER")
    if root is None:
        errors.append("missing V4_AIRCRAFT_MASTER")

    manifold_report: dict[str, int] = {}
    for name in PRIMARY_CLOSED_MESHES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            errors.append(f"missing primary mesh {name}")
            continue
        edge_count = non_manifold_edge_count(obj)
        manifold_report[name] = edge_count
        if edge_count:
            errors.append(f"{name} has {edge_count} non-manifold base-mesh edges")

    for name in REQUIRED_JOINTS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "EMPTY":
            errors.append(f"missing joint/datum {name}")

    unparented_aircraft_objects: list[str] = []
    if root is not None:
        allowed_unparented = {
            root.name,
            "Final_Presentation_Platform",
            "V4_Review_Camera",
            "Key_Softbox",
            "Fill_Softbox",
            "Rim_Softbox",
        }
        for obj in bpy.context.scene.objects:
            if obj.name in allowed_unparented:
                continue
            if obj.parent is not root:
                unparented_aircraft_objects.append(obj.name)
        if unparented_aircraft_objects:
            errors.append("aircraft objects outside master assembly: " + ", ".join(unparented_aircraft_objects))

    fuselage = bpy.data.objects.get("V4_Continuous_Fuselage_Shell")
    livery_nodes_ok = False
    if fuselage is not None and fuselage.data.materials:
        material = fuselage.data.materials[0]
        livery_nodes_ok = material is not None and material.use_nodes and any(
            node.label == "Ivory and turquoise aircraft enamel" for node in material.node_tree.nodes
        )
    if not livery_nodes_ok:
        errors.append("integrated fuselage livery shader is missing")

    missing_renders = [str(path.name) for path in RENDER_PATHS if not path.exists() or path.stat().st_size < 100_000]
    if missing_renders:
        errors.append("missing or undersized renders: " + ", ".join(missing_renders))

    report = {
        "blend": str(BLEND_PATH),
        "blender_version": bpy.app.version_string,
        "scene_objects": len(bpy.context.scene.objects),
        "assembly_children": sum(1 for obj in bpy.context.scene.objects if root is not None and obj.parent is root),
        "primary_non_manifold_edges": manifold_report,
        "required_joint_count": len(REQUIRED_JOINTS),
        "integrated_livery_shader": livery_nodes_ok,
        "render_sizes_bytes": {path.name: path.stat().st_size if path.exists() else 0 for path in RENDER_PATHS},
        "errors": errors,
    }
    print("V4_QA " + json.dumps(report, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

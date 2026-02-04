bl_info = {
    "name": "Export Object Animation to JSON/TXT (stable Euler + safe axis swap)",
    "author": "ChatGPT",
    "version": (2, 5),
    "blender": (3, 0, 0),
    "location": "Object > Export Animation to JSON/TXT",
    "description": "Fixes random 180° flips by unwrapping Euler XYZ BEFORE axis swap. Axis swap is now presentation-only and stable.",
    "category": "Animation",
}

import bpy
import json
import math
from bpy_extras.io_utils import ExportHelper
from bpy.props import (
    StringProperty, IntProperty, BoolProperty,
    FloatProperty, EnumProperty
)

EXPORT_FPS = 24.0

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def closest_euler_equiv(prev_vals, cur_vals, in_degrees=True, max_shift=1):
    if prev_vals is None:
        return list(cur_vals)

    full = 360.0 if in_degrees else 2.0 * math.pi
    best = None
    best_dist = None

    for kx in range(-max_shift, max_shift + 1):
        for ky in range(-max_shift, max_shift + 1):
            for kz in range(-max_shift, max_shift + 1):
                cand = (
                    cur_vals[0] + kx * full,
                    cur_vals[1] + ky * full,
                    cur_vals[2] + kz * full,
                )
                dx = cand[0] - prev_vals[0]
                dy = cand[1] - prev_vals[1]
                dz = cand[2] - prev_vals[2]
                dist = dx*dx + dy*dy + dz*dz
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = cand

    return list(best)

def apply_swap_mapping(vec, mapping):
    idx = {'X': 0, 'Y': 1, 'Z': 2}
    return [vec[idx[c]] for c in mapping]

SWAP_ITEMS = [
    ('XYZ', 'XYZ (no swap)', ''),
    ('XZY', 'XZY', ''),
    ('YXZ', 'YXZ', ''),
    ('YZX', 'YZX', ''),
    ('ZXY', 'ZXY', ''),
    ('ZYX', 'ZYX', ''),
]

# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class ExportAnimJSON(bpy.types.Operator, ExportHelper):
    bl_idname = "export_animation.anim_to_json"
    bl_label = "Export Animation to JSON/TXT"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json;*.txt", options={'HIDDEN'})

    start_frame: IntProperty(default=1)
    end_frame: IntProperty(default=250)
    step: IntProperty(default=1, min=1)

    export_selected: BoolProperty(default=True)
    use_world_space: BoolProperty(default=False)

    export_rotation: BoolProperty(default=True)
    export_degrees: BoolProperty(default=True)

    invert_rot_x: BoolProperty(default=False)
    invert_rot_y: BoolProperty(default=False)
    invert_rot_z: BoolProperty(default=False)

    rotation_swap: EnumProperty(
        name="Swap XYZ to (Rotation)",
        items=SWAP_ITEMS,
        default='XYZ'
    )

    zero_rot_at_start: BoolProperty(default=False)

    use_axis_unwrap: BoolProperty(default=True)
    unwrap_max_shift: IntProperty(default=1, min=0, max=3)

    # ------------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        depsgraph = context.evaluated_depsgraph_get()
        orig_frame = scene.frame_current

        objects = context.selected_objects if self.export_selected else [context.active_object]
        objects = [o for o in objects if o]

        if not objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}

        data = {"animation_length": (self.end_frame - self.start_frame + 1) / EXPORT_FPS,
                "bones": {}}

        prev_quat = {}
        prev_euler_xyz = {}

        # --------------------------------------------

        for obj in objects:
            rot_track = {}

            # base rotation
            scene.frame_set(self.start_frame)
            eval_obj = obj.evaluated_get(depsgraph)
            q0 = eval_obj.matrix_world.to_quaternion() if self.use_world_space else eval_obj.rotation_euler.to_quaternion()
            e0 = q0.to_euler('XYZ')

            base_xyz = [e0.x, e0.y, e0.z]
            if self.export_degrees:
                base_xyz = [math.degrees(v) for v in base_xyz]

            # ----------------------------------------

            for frame in range(self.start_frame, self.end_frame + 1, self.step):
                scene.frame_set(frame)
                eval_obj = obj.evaluated_get(depsgraph)

                q = eval_obj.matrix_world.to_quaternion() if self.use_world_space else eval_obj.rotation_euler.to_quaternion()

                if obj.name in prev_quat and prev_quat[obj.name].dot(q) < 0:
                    q = -q
                prev_quat[obj.name] = q.copy()

                e = q.to_euler('XYZ')
                xyz = [e.x, e.y, e.z]

                if self.export_degrees:
                    xyz = [math.degrees(v) for v in xyz]

                if self.invert_rot_x: xyz[0] *= -1
                if self.invert_rot_y: xyz[1] *= -1
                if self.invert_rot_z: xyz[2] *= -1

                if self.use_axis_unwrap:
                    xyz = closest_euler_equiv(
                        prev_euler_xyz.get(obj.name),
                        xyz,
                        self.export_degrees,
                        self.unwrap_max_shift
                    )

                prev_euler_xyz[obj.name] = xyz.copy()

                # ZEROING happens in XYZ space
                if self.zero_rot_at_start:
                    xyz = [
                        xyz[0] - base_xyz[0],
                        xyz[1] - base_xyz[1],
                        xyz[2] - base_xyz[2],
                    ]

                # AXIS SWAP IS LAST (presentation only)
                final_rot = apply_swap_mapping(xyz, self.rotation_swap)

                rot_track[f"{frame / EXPORT_FPS:.4f}"] = {
                    "vector": [round(v, 5) for v in final_rot]
                }

            data["bones"][obj.name] = {"rotation": rot_track}

        # --------------------------------------------

        out = {
            "format_version": "1.9.0",
            "animations": {"animation": data}
        }

        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4)

        scene.frame_set(orig_frame)
        self.report({'INFO'}, "Export complete")
        return {'FINISHED'}

# ------------------------------------------------------------

def menu_func(self, context):
    self.layout.operator(ExportAnimJSON.bl_idname)

def register():
    bpy.utils.register_class(ExportAnimJSON)
    bpy.types.VIEW3D_MT_object.append(menu_func)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    bpy.utils.unregister_class(ExportAnimJSON)

if __name__ == "__main__":
    register()

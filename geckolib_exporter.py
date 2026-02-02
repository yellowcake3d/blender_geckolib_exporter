bl_info = {
    "name": "Export Object Animation to JSON/TXT (patched with Swap XYZ dropdown)",
    "author": "ChatGPT",
    "version": (2, 4),
    "blender": (3, 0, 0),
    "location": "Object > Export Animation to JSON/TXT",
    "description": "Export rotation/scale/position animation to JSON. Uses quaternion->Euler conversion + quaternion continuity + closest-equivalent Euler search to avoid jumps. Adds 'Swap XYZ to' dropdown for rotation/scale/position.",
    "category": "Animation",
}

import bpy
import json
import math
from bpy_extras.io_utils import ExportHelper
from bpy.props import (StringProperty, IntProperty, BoolProperty,
                       FloatProperty, EnumProperty)
from mathutils import Quaternion

EXPORT_FPS = 24.0

def closest_euler_equiv(prev_vals, cur_vals, in_degrees=True, max_shift=1):
    """
    Find the Euler-equivalent of cur_vals that is numerically closest to prev_vals by
    adding/subtracting full rotations on each axis.
    - prev_vals: previous exported [x,y,z] or None
    - cur_vals: current candidate [x,y,z]
    - in_degrees: True if values are in degrees, False if radians
    - max_shift: how many full-rotations to try per axis (1 tries -1,0,+1)
    Returns adjusted [x,y,z].
    """
    if prev_vals is None:
        return cur_vals
    if in_degrees:
        full = 360.0
    else:
        full = 2.0 * math.pi

    best = None
    best_dist = None
    rng = range(-max_shift, max_shift + 1)
    for kx in rng:
        for ky in rng:
            for kz in rng:
                cand_x = cur_vals[0] + kx * full
                cand_y = cur_vals[1] + ky * full
                cand_z = cur_vals[2] + kz * full
                dx = cand_x - prev_vals[0]
                dy = cand_y - prev_vals[1]
                dz = cand_z - prev_vals[2]
                dist = dx * dx + dy * dy + dz * dz
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = (cand_x, cand_y, cand_z)
    return list(best)

def apply_swap_mapping(vec, mapping):
    """
    vec: iterable with 3 elements (x,y,z)
    mapping: string denoting order e.g. 'XYZ','XZY','YXZ', etc.
    Returns list [new_x, new_y, new_z] where each is taken from vec according to mapping.
    Example: mapping 'YXZ' -> returns [vec[1], vec[0], vec[2]]
    """
    idx = {'X': 0, 'Y': 1, 'Z': 2}
    return [vec[idx[c]] for c in mapping]

SWAP_ITEMS = [
    ('XYZ', 'XYZ (no swap)', 'No axis swap'),
    ('XZY', 'XZY', 'Swap Y and Z positions'),
    ('YXZ', 'YXZ', 'Swap X and Y positions'),
    ('YZX', 'YZX', 'Reorder to Y,Z,X'),
    ('ZXY', 'ZXY', 'Reorder to Z,X,Y'),
    ('ZYX', 'ZYX', 'Reorder to Z,Y,X'),
]

class ExportAnimJSON(bpy.types.Operator, ExportHelper):
    """Export object rotation (and scale/position) animation to JSON/TXT"""
    bl_idname = "export_animation.anim_to_json"
    bl_label = "Export Animation to JSON/TXT"

    filename_ext = ".txt"
    filter_glob: StringProperty(default="*.txt;*.json", options={'HIDDEN'})

    fps: IntProperty(name="FPS (UI only)", default=24, min=1)
    start_frame: IntProperty(name="Start Frame", default=1)
    end_frame: IntProperty(name="End Frame", default=250)
    step: IntProperty(name="Frame Step", default=1, min=1)
    export_selected: BoolProperty(name="Export All Selected", default=True)
    use_world_space: BoolProperty(name="Use World Space", default=False)

    export_rotation: BoolProperty(name="Export Rotation", default=True)
    export_degrees: BoolProperty(name="Export Rotation in Degrees", default=True)
    invert_rot_x: BoolProperty(name="Invert Rotation X", default=False)
    invert_rot_y: BoolProperty(name="Invert Rotation Y", default=False)
    invert_rot_z: BoolProperty(name="Invert Rotation Z", default=False)
    # rotation swap dropdown
    rotation_swap: EnumProperty(
        name="Swap XYZ to (Rotation)",
        description="Permute exported rotation axes",
        items=SWAP_ITEMS,
        default='XYZ',
    )
    zero_rot_at_start: BoolProperty(name="Zero Rotation at Start", default=False)

    # axis unwrap/search toggle
    use_axis_unwrap: BoolProperty(
        name="Use Axis Unwrap (closest-euler search)",
        description="Adjust exported Euler angles per-axis to be closest to previous exported frame (fixes Euler wrap jumps).",
        default=True,
    )

    export_scale: BoolProperty(name="Export Scale", default=False)
    normalize_scale_at_start: BoolProperty(name="Normalize Scale at Start", default=False)
    # scale swap dropdown
    scale_swap: EnumProperty(
        name="Swap XYZ to (Scale)",
        description="Permute exported scale axes",
        items=SWAP_ITEMS,
        default='XYZ',
    )

    export_position: BoolProperty(name="Export Position", default=False)
    pos_multiplier: FloatProperty(name="Position Multiplier", default=1.0, precision=3, step=1)
    invert_pos_x: BoolProperty(name="Invert Pos X", default=False)
    invert_pos_y: BoolProperty(name="Invert Pos Y", default=False)
    invert_pos_z: BoolProperty(name="Invert Pos Z", default=False)
    # position swap dropdown
    position_swap: EnumProperty(
        name="Swap XYZ to (Position)",
        description="Permute exported position axes",
        items=SWAP_ITEMS,
        default='XYZ',
    )

    # optional: expose search depth (max_shift) as property if you want control (default 1)
    unwrap_max_shift: IntProperty(
        name="Unwrap Max Shift",
        description="How many full-rotations to try per axis when searching closest equivalent (1 = ±360°, 2 = ±720°)",
        default=1,
        min=0,
        max=3,
    )

    def invoke(self, context, event):
        scene = context.scene
        self.start_frame = scene.frame_start
        self.end_frame = scene.frame_end
        return ExportHelper.invoke(self, context, event)

    def _get_scale_vector(self, obj):
        try:
            if self.use_world_space:
                return obj.matrix_world.to_scale()
            else:
                return obj.scale.copy()
        except Exception:
            return obj.scale.copy()

    def _get_position_vector(self, obj):
        try:
            if self.use_world_space:
                return obj.matrix_world.to_translation()
            else:
                return obj.location.copy()
        except Exception:
            return obj.location.copy()

    def execute(self, context):
        scene = context.scene
        orig_frame = scene.frame_current

        if self.export_selected:
            objects = context.selected_objects
        else:
            obj = context.active_object
            objects = [obj] if obj else []

        if not objects:
            self.report({'WARNING'}, "No objects to export (select an object first).")
            return {'CANCELLED'}

        start = int(self.start_frame)
        end = int(self.end_frame)
        if end < start:
            start, end = end, start

        frame_count = (end - start + 1)
        animation_length_seconds = frame_count / EXPORT_FPS

        animation_data = {"animation_length": animation_length_seconds, "bones": {}}

        depsgraph = context.evaluated_depsgraph_get()
        prev_quats = {}           # quaternion continuity
        prev_exported_rot = {}    # store last exported Euler vector (post-processing) per object

        for obj in objects:
            rotation_data = {} if self.export_rotation else None
            scale_data = {} if self.export_scale else None
            position_data = {} if self.export_position else None

            # base samples at start
            scene.frame_set(start)
            if self.export_position:
                base_pos = self._get_position_vector(obj)
                base_pos_vec = (base_pos[0], base_pos[1], base_pos[2])
            else:
                base_pos_vec = (0.0, 0.0, 0.0)

            if self.export_rotation:
                eval_start = obj.evaluated_get(depsgraph)
                if self.use_world_space:
                    q0 = eval_start.matrix_world.to_quaternion()
                else:
                    if getattr(eval_start, "rotation_mode", "") == 'QUATERNION':
                        q0 = eval_start.rotation_quaternion.copy()
                    else:
                        q0 = eval_start.rotation_euler.to_quaternion()
                e0 = q0.to_euler('XYZ')
                r0x, r0y, r0z = e0.x, e0.y, e0.z
                if self.export_degrees:
                    r0x, r0y, r0z = math.degrees(r0x), math.degrees(r0y), math.degrees(r0z)
                if self.invert_rot_x: r0x = -r0x
                if self.invert_rot_y: r0y = -r0y
                if self.invert_rot_z: r0z = -r0z
                # apply rotation swap mapping to base
                base_rot_vec = tuple(apply_swap_mapping((r0x, r0y, r0z), self.rotation_swap))
            else:
                base_rot_vec = (0.0, 0.0, 0.0)

            if self.export_scale:
                s0 = self._get_scale_vector(obj)
                s0x, s0y, s0z = s0[0], s0[1], s0[2]
                # apply scale swap mapping to base scale
                base_scale_vec = tuple(apply_swap_mapping((s0x, s0y, s0z), self.scale_swap))
            else:
                base_scale_vec = (1.0, 1.0, 1.0)

            # iterate frames
            for frame in range(start, end + 1, self.step):
                scene.frame_set(frame)

                # ROTATION (quaternion continuity -> euler -> conversions -> zeroing)
                if self.export_rotation:
                    eval_obj = obj.evaluated_get(depsgraph)
                    if self.use_world_space:
                        q = eval_obj.matrix_world.to_quaternion()
                    else:
                        if getattr(eval_obj, "rotation_mode", "") == 'QUATERNION':
                            q = eval_obj.rotation_quaternion.copy()
                        else:
                            q = eval_obj.rotation_euler.to_quaternion()

                    # quaternion-sign continuity
                    prevq = prev_quats.get(obj.name)
                    if prevq is not None and prevq.dot(q) < 0.0:
                        q = -q
                    prev_quats[obj.name] = q.copy()

                    e = q.to_euler('XYZ')
                    rx, ry, rz = e.x, e.y, e.z

                    if self.export_degrees:
                        rx, ry, rz = math.degrees(rx), math.degrees(ry), math.degrees(rz)

                    if self.invert_rot_x: rx = -rx
                    if self.invert_rot_y: ry = -ry
                    if self.invert_rot_z: rz = -rz

                    # apply rotation swap mapping BEFORE zeroing so subtraction matches order
                    rx, ry, rz = apply_swap_mapping((rx, ry, rz), self.rotation_swap)

                    if self.zero_rot_at_start:
                        rx -= base_rot_vec[0]
                        ry -= base_rot_vec[1]
                        rz -= base_rot_vec[2]

                    # choose the Euler-equivalent closest to previous exported Euler (search-based)
                    prev_vals = prev_exported_rot.get(obj.name)
                    if self.use_axis_unwrap:
                        rx, ry, rz = closest_euler_equiv(prev_vals, [rx, ry, rz], in_degrees=self.export_degrees, max_shift=self.unwrap_max_shift)

                    prev_exported_rot[obj.name] = [rx, ry, rz]

                    rot_vec = [round(rx, 5), round(ry, 5), round(rz, 5)]
                    rot_key = f"{frame / EXPORT_FPS:.4f}"
                    rotation_data[rot_key] = {"vector": rot_vec}

                # SCALE
                if self.export_scale:
                    s = self._get_scale_vector(obj)
                    sx, sy, sz = s[0], s[1], s[2]

                    # normalize scale at start: divide by base_scale so start becomes [1,1,1]
                    if self.normalize_scale_at_start:
                        bsx = base_scale_vec[0] if base_scale_vec[0] != 0 else 1.0
                        bsy = base_scale_vec[1] if base_scale_vec[1] != 0 else 1.0
                        bsz = base_scale_vec[2] if base_scale_vec[2] != 0 else 1.0
                        sx = sx / bsx
                        sy = sy / bsy
                        sz = sz / bsz

                    # apply scale swap mapping
                    sx, sy, sz = apply_swap_mapping((sx, sy, sz), self.scale_swap)

                    scale_vec = [round(sx, 5), round(sy, 5), round(sz, 5)]
                    scale_key = f"{frame / EXPORT_FPS:.4f}"
                    scale_data[scale_key] = {"vector": scale_vec}

                # POSITION
                if self.export_position:
                    p = self._get_position_vector(obj)
                    px = p[0] - base_pos_vec[0]
                    py = p[1] - base_pos_vec[1]
                    pz = p[2] - base_pos_vec[2]

                    # multiplier (single scalar)
                    px *= self.pos_multiplier
                    py *= self.pos_multiplier
                    pz *= self.pos_multiplier

                    # inversion after multiplier
                    if self.invert_pos_x: px = -px
                    if self.invert_pos_y: py = -py
                    if self.invert_pos_z: pz = -pz

                    # apply position swap mapping
                    px, py, pz = apply_swap_mapping((px, py, pz), self.position_swap)

                    pos_vec = [round(px, 5), round(py, 5), round(pz, 5)]
                    pos_key = f"{(frame - start) / EXPORT_FPS:.4f}"
                    position_data[pos_key] = {"vector": pos_vec}

            # assemble object structure
            obj_struct = {}
            if rotation_data is not None: obj_struct["rotation"] = rotation_data
            if scale_data is not None: obj_struct["scale"] = scale_data
            if position_data is not None: obj_struct["position"] = position_data

            animation_data["bones"][obj.name] = obj_struct

        # write file
        export_root = {
            "format_version": "1.8.0",
            "animations": {
                "animation": animation_data
            }
        }

        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(export_root, f, indent=4)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write file: {e}")
            scene.frame_set(orig_frame)
            return {'CANCELLED'}

        scene.frame_set(orig_frame)
        self.report({'INFO'}, f"Animation exported to {self.filepath}")
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(ExportAnimJSON.bl_idname, text="Export Animation to JSON/TXT (patched)")

classes = (ExportAnimJSON,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(menu_func)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

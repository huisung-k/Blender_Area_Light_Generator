bl_info = {
    "name": "Mesh Island Area Light Generator",
    "author": "Alex Kim (HUISUNG)",
    "version": (1, 0, 0),
    "blender": (5, 2, 4),
    "location": "View3D > Sidebar > Lighting",
    "description": "Generate area lights at disconnected mesh islands",
    "category": "Lighting",
}

import bpy
import math
from mathutils import Vector
from bpy.props import (
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
)

TAG = "huisung_generated_area_light"
OUTPUT_COLLECTION = "Generated_Area_Lights"


def mesh_islands(mesh):
    parent = list(range(len(mesh.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for edge in mesh.edges:
        a, b = find(edge.vertices[0]), find(edge.vertices[1])
        if a != b:
            parent[b] = a

    groups = {}
    for vertex in mesh.vertices:
        groups.setdefault(find(vertex.index), []).append(vertex.index)
    return list(groups.values())


class ALGEN_Settings(bpy.types.PropertyGroup):
    power: FloatProperty(name="Power (W)", default=100.0, min=0.0)
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.45, 0.8, 1.0))
    size: FloatProperty(
        name="Diameter",
        default=1.0,
        min=0.001,
        unit='LENGTH'
    )
    spread: FloatProperty(name="Spread", default=125.0, min=1.0, max=180.0, description="Spread angle in degrees")
    offset: FloatProperty(name="Vertical Offset", default=-0.11, unit='LENGTH')
    replace_previous: BoolProperty(name="Replace Previously Generated Lights", default=True)


class ALGEN_OT_generate(bpy.types.Operator):
    bl_idname = "algen.generate"
    bl_label = "Generate Area Lights"
    bl_description = "Generate one area light per disconnected mesh island"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.algen_settings
        sources = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not sources:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}

        # Analyze first, without modifying the scene, to avoid deleting prior results on failure.
        depsgraph = context.evaluated_depsgraph_get()
        placements = []
        try:
            for source in sources:
                evaluated = source.evaluated_get(depsgraph)
                mesh = evaluated.to_mesh()

                if mesh is None:
                    continue

                try:
                    for indices in mesh_islands(mesh):
                        if indices:
                            center = sum(
                                (mesh.vertices[i].co for i in indices),
                                Vector()
                            ) / len(indices)

                            world_center = source.matrix_world @ center
                            placements.append(world_center)

                finally:
                    evaluated.to_mesh_clear()

        except Exception as exc:
            self.report({'ERROR'}, f"Mesh analysis failed: {exc}")
            return {'CANCELLED'}

        if not placements:
            self.report({'WARNING'}, "No mesh islands found")
            return {'CANCELLED'}

        collection = bpy.data.collections.get(OUTPUT_COLLECTION)
        if collection is None:
            collection = bpy.data.collections.new(OUTPUT_COLLECTION)
            context.scene.collection.children.link(collection)
        elif collection.name not in {c.name for c in context.scene.collection.children_recursive}:
            context.scene.collection.children.link(collection)

        # Only remove tagged light objects; preserve unrelated objects in the collection.
        if settings.replace_previous:
            for obj in list(collection.objects):
                if obj.get(TAG, False) and obj.type == 'LIGHT':
                    light_data = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if light_data and light_data.users == 0:
                        bpy.data.lights.remove(light_data)

        created = 0
        for center in placements:
            light_data = bpy.data.lights.new(f"Area_Light_{created:03d}", type='AREA')
            light_data.energy = settings.power
            light_data.color = tuple(settings.color)
            light_data.shape = 'DISK'
            light_data.size = settings.size
            if hasattr(light_data, 'spread'):
                light_data.spread = math.radians(settings.spread)
            light_obj = bpy.data.objects.new(light_data.name, light_data)
            collection.objects.link(light_obj)
            light_obj[TAG] = True
            light_obj.location = center + Vector((0, 0, settings.offset))
            light_obj.rotation_euler = (0.0, 0.0, 0.0)
            created += 1
            
        self.report({'INFO'}, f"Generated {created} area lights from {len(sources)} meshes")
        return {'FINISHED'}


class ALGEN_PT_panel(bpy.types.Panel):
    bl_label = "Area Light Generator"
    bl_idname = "ALGEN_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lighting'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.algen_settings
        layout.label(text="Select one or more mesh objects")
        col = layout.column(align=True)
        col.prop(settings, 'power')
        col.prop(settings, 'color')
        col.prop(settings, 'size')
        col.prop(settings, 'spread')
        col.prop(settings, 'offset')
        col.separator()
        col.prop(settings, 'replace_previous')
        layout.separator()
        layout.operator('algen.generate', icon='LIGHT_AREA')


CLASSES = (ALGEN_Settings, ALGEN_OT_generate, ALGEN_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.algen_settings = PointerProperty(type=ALGEN_Settings)


def unregister():
    if hasattr(bpy.types.Scene, 'algen_settings'):
        del bpy.types.Scene.algen_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()

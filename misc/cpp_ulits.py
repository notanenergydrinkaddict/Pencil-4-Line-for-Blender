# SPDX-License-Identifier: GPL-2.0-or-later
# The Original Code is Copyright (C) P SOFTHOUSE Co., Ltd. All rights reserved.

import bpy
import math
from ..node_tree.misc.AttrOverride import get_overrided_attr

def copy_props(py_instance, cpp_instance, instance_dict=None, context: bpy.types.Context=None, depsgraph: bpy.types.Depsgraph=None):
    for prop_name in (x for x in dir(cpp_instance) if not x.startswith("_")):
        if not hasattr(py_instance, prop_name):
            # 該当するプロパティがPython側に存在しない (このコードパスを通るのは基本的に不具合である)
            print(f"Not transferred: {py_instance.name}.{prop_name} - Property not found.")
            continue
        py_value = getattr(py_instance, prop_name)
        py_type = type(py_value)
        if context is not None or depsgraph is not None:
            py_value = get_overrided_attr(py_instance, prop_name, context=context, depsgraph=depsgraph)
        cpp_value = getattr(cpp_instance, prop_name)
        cpp_type = type(cpp_value)

        # primitive
        if cpp_type in [bool, int, float]:
            if py_instance.bl_rna.properties[prop_name].subtype == "ANGLE":
                py_value = math.degrees(py_value)
            elif py_instance.bl_rna.properties[prop_name].subtype == "PERCENTAGE":
                py_value *= 0.01
            setattr(cpp_instance, prop_name, py_value)
        # enum
        elif cpp_type.__name__.startswith("pcl4_enum_"):
            enum_items = py_instance.bl_rna.properties[prop_name].enum_items
            raw_value = next(x.value for x in enum_items if x.identifier == py_value)
            setattr(cpp_instance, prop_name, cpp_type(raw_value))
        # vector / color
        elif cpp_type is list and len(cpp_value) == len(py_value):
            setattr(cpp_instance, prop_name, py_value)
        # curve
        elif cpp_type is list and len(cpp_value) > 1 and py_type is str and "curve" in prop_name:
            setattr(cpp_instance, prop_name, py_instance.evaluate_curve(py_value, len(cpp_value)))
        # socket
        elif cpp_type is type(None) and py_type is str:
            if context is not None or depsgraph is not None:
                py_value = py_instance.filtered_socket_id(py_instance.__class__.bl_rna.properties[prop_name].default, context=context, depsgraph=depsgraph)
            child_node = next((x.get_connected_node(ignore_muted_link = True) for x in py_instance.inputs if x.identifier == py_value), None)
            if instance_dict is not None and child_node is not None and child_node in instance_dict:
                child_cpp_instance = instance_dict[child_node]
                setattr(cpp_instance, prop_name, child_cpp_instance)
        # socket(multi)
        elif cpp_type is list and py_type is str:
            if context is not None or depsgraph is not None:
                py_value = py_instance.filtered_socket_id(py_instance.__class__.bl_rna.properties[prop_name].default, context=context, depsgraph=depsgraph)
            if instance_dict is not None:
                child_nodes = (x.get_connected_node(ignore_muted_link = True) for x in py_instance.inputs if x.identifier.startswith(py_value))
                for n in child_nodes:
                    if n is None or n not in instance_dict:
                        continue
                    child_cpp_instance = instance_dict[n]
                    cpp_value.append(child_cpp_instance)
                setattr(cpp_instance, prop_name, cpp_value)
        # string
        elif cpp_type is str and py_type is str:
            setattr(cpp_instance, prop_name, py_value)
        # object
        elif cpp_type is type(None) and py_type is bpy.types.Object:
            if py_value is not None and depsgraph is not None:
                eval_object = next((x.object for x in depsgraph.object_instances if x.object.original.override_library is not None and x.object.original.override_library.reference == py_value), depsgraph.id_eval_get(py_value)) 
                if eval_object is not None:
                    py_value = eval_object
            setattr(cpp_instance, prop_name, py_value)
        # objects or materials
        elif cpp_type is list and py_type.__name__ == "bpy_prop_collection_idprop":
            for o in py_value:
                cpp_value.append(o.content)
            setattr(cpp_instance, prop_name, cpp_value)
        # image
        elif cpp_type is type(None) and py_type is bpy.types.Image:
            setattr(cpp_instance, prop_name, py_value)
        # objectやtextureが代入されていないとき
        elif cpp_type is type(None) and py_type is type(None):
            pass
        else:
            # プロパティの転送条件漏れ (このコードパスを通るのは基本的に不具合である)
            print(f"Not transferred: {prop_name} - py:{py_type} -> cpp:{cpp_type}")    
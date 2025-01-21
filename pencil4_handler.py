# SPDX-License-Identifier: GPL-2.0-or-later
# The Original Code is Copyright (C) P SOFTHOUSE Co., Ltd. All rights reserved.


if "bpy" in locals():
    import imp
    imp.reload(pencil4_render_session)
    imp.reload(pencil4_render_images)
    imp.reload(pencil4_viewport)
else:
    from . import pencil4_render_session
    from . import pencil4_render_images
    from . import pencil4_viewport

from .pencil4_render_session import Pencil4RenderSession as RenderSession
from .merge_helper import merge_helper
from .node_tree import PencilNodeTree

import threading
import bpy
from bpy.app.handlers import persistent

__session: RenderSession = None
__depsgraph_update_lock = threading.RLock()

def append():
    bpy.app.handlers.render_pre.append(on_pre_render)
    bpy.app.handlers.render_cancel.append(on_render_cancel)
    bpy.app.handlers.render_complete.append(on_render_complete)
    bpy.app.handlers.frame_change_post.append(on_post_frame_change)
    bpy.app.handlers.save_pre.append(on_save_pre)
    bpy.app.handlers.save_post.append(on_save_post)
    bpy.app.handlers.load_post.append(on_load_post)
    bpy.app.handlers.depsgraph_update_pre.append(on_depsgraph_update_pre)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update_post)

def remove():
    bpy.app.handlers.render_pre.remove(on_pre_render)
    bpy.app.handlers.render_cancel.remove(on_render_cancel)
    bpy.app.handlers.render_complete.remove(on_render_complete)
    bpy.app.handlers.frame_change_post.remove(on_post_frame_change)
    bpy.app.handlers.save_pre.remove(on_save_pre)
    bpy.app.handlers.save_post.remove(on_save_post)
    bpy.app.handlers.load_post.remove(on_load_post)
    bpy.app.handlers.depsgraph_update_pre.remove(on_depsgraph_update_pre)
    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update_post)

def in_render_session() -> bool:
    return __session is not None

@persistent
def on_pre_render(scene: bpy.types.Scene):
    global __session
    global __depsgraph_update_lock
    if __session is None:
        with __depsgraph_update_lock:
            hide_shader_nodes_on_render()
            __session = RenderSession()
            pencil4_viewport.ViewportLineRenderManager.in_render_session = True
            pencil4_render_images.correct_duplicated_output_images(scene)
            pencil4_render_images.setup_images(scene)
    else:
        __session.cleanup_frame()

@persistent
def on_render_cancel(scene: bpy.types.Scene):
    global __session
    if __session is not None:
        __session.cleanup_all()
        __session = None
        pencil4_render_images.unpack_images(scene)
        pencil4_viewport.ViewportLineRenderManager.in_render_session = False
        restore_hidden_shader_nodes()

@persistent
def on_render_complete(scene: bpy.types.Scene):
    global __session
    if __session is not None:
        __session.cleanup_all()
        __session = None
        pencil4_render_images.unpack_images(scene)
        pencil4_viewport.ViewportLineRenderManager.in_render_session = False
        restore_hidden_shader_nodes()

@persistent
def on_post_frame_change(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    global __session
    if __session is not None:
        __session.draw_line(depsgraph)
    pencil4_viewport.ViewportLineRenderManager.invalidate_objects_cache()

@persistent
def on_save_pre(dummy):
    pencil4_viewport.on_save_pre()
    pencil4_render_images.ViewLayerLineOutputs.on_save_pre()
    merge_helper.link()
    PencilNodeTree.set_first_update_flag()

@persistent
def on_save_post(dummy):
    merge_helper.unlink()
    PencilNodeTree.clear_first_update_flag()

@persistent
def on_load_post(dummy):
    pencil4_viewport.on_load_post()
    pencil4_render_images.ViewLayerLineOutputs.on_load_post()
    merge_helper.unlink()
    PencilNodeTree.correct_curve_tree()
    PencilNodeTree.migrate_nodes()

@persistent
def on_depsgraph_update_pre(scene: bpy.types.Scene):
    global __depsgraph_update_lock
    __depsgraph_update_lock.acquire()
    pencil4_viewport.ViewportLineRenderManager.invalidate_objects_cache()

@persistent
def on_depsgraph_update_post(scene: bpy.types.Scene):
    global __depsgraph_update_lock
    __depsgraph_update_lock.release()

# Blender 3.5 ~ 4.1 では、レンダリング中に特定のシェーダーノードを表示するとフリーズする問題がある
# 対策として、フリーズの原因になる表示中のシェーダーノードを隠す
__hidden_shader_nodes = None
_freeze_shader_nodes = { "ShaderNodeUVMap", "ShaderNodeVertexColor" }
def hide_shader_nodes_on_render():
    global __hidden_shader_nodes
    if bpy.app.background or bpy.context.scene.render.use_lock_interface:
        return
    __hidden_shader_nodes = []
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == "NODE_EDITOR":
                    for space in area.spaces:
                        if space.type == "NODE_EDITOR" and space.tree_type == "ShaderNodeTree" and space.edit_tree is not None:
                            for node in space.edit_tree.nodes:
                                if not node.hide and node.bl_idname in _freeze_shader_nodes:
                                    node.hide = True
                                    __hidden_shader_nodes.append((space.edit_tree, node.name))

def restore_hidden_shader_nodes():
    global __hidden_shader_nodes
    if __hidden_shader_nodes is None:
        return
    hidden_shader_nodes = __hidden_shader_nodes
    __hidden_shader_nodes = None
    def restore_impl():
        for tree, node_name in hidden_shader_nodes:
            node = tree.nodes.get(node_name)
            if node is not None:
                node.hide = False
    bpy.app.timers.register(restore_impl, first_interval=0.0)

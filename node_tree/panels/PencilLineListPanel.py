# SPDX-License-Identifier: GPL-2.0-or-later
# The Original Code is Copyright (C) P SOFTHOUSE Co., Ltd. All rights reserved.

import itertools
import bpy
from ..nodes.LineNode import LineNode
from ..nodes.LineSetNode import LineSetNode
from ..nodes.BrushSettingsNode import BrushSettingsNode
from ..nodes.BrushDetailNode import BrushDetailNode
from ..PencilNodeTree import PencilNodeTree
from . import LineNodePanel
from ..misc.NamedRNAStruct import NamedRNAStruct
from ...i18n import Translation
from ..nodes.PencilNodeMixin import PencilNodeMixin
from ..misc.GuiUtils import layout_prop
from ..misc import AttrOverride
from ... import pencil4_render_session
from ..PencilNodePreview import PreviewManager

class PCL4_UL_LineListView(bpy.types.UIList):
    has_ovveride: bpy.props.BoolProperty(default=False)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row2 = row.row()
        row2.alignment = "LEFT"
        row2.label(text=" ")
        row2 = row.row()
        row2.alignment = "CENTER"
        layout_prop(context, row2, item, "is_active", preserve_icon_space=self.has_ovveride, preserve_icon_space_emboss=False, text="")
        row.prop(item, "name", text="", emboss=False, translate=False)

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, propname):
        nodes = getattr(data, propname)
        lines = PencilNodeTree.tree_from_context(context).enumerate_lines()

        self.has_ovveride = False
        flt_flags = []
        flt_neworder = []
        another_node_index = len(lines)

        for node in nodes:
            if isinstance(node, LineNode):
                flt_flags.append(self.bitflag_filter_item)
                flt_neworder.append(lines.index(node))
                self.has_ovveride |= AttrOverride.is_overrided(node, "is_active", context)
            else:
                flt_flags.append(0)
                flt_neworder.append(another_node_index)
                another_node_index = another_node_index + 1

        return flt_flags, flt_neworder        


class PCL4_PT_PencilLineList_mixin:
    @classmethod
    def linelist_poll(cls, context):
        return isinstance(context.space_data.edit_tree, PencilNodeTree)

    @classmethod
    def line_node(cls, context):
        return isinstance(context.space_data.edit_tree, PencilNodeTree) and\
               PencilNodeTree.tree_from_context(context).get_selected_line()


class PCL4_PT_PencilLineList(PCL4_PT_PencilLineList_mixin, bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Pencil+ 4 Line"
    bl_options = {"HIDE_HEADER"}
    bl_label = ""
    bl_order = 0

    @classmethod
    def poll(cls, context):
        if context.space_data.tree_type != PencilNodeTree.bl_idname:
            return False

        #　ライン描画のノードツリー実体が存在しない場合、強制的にノードツリーを新規生成する
        if not PencilNodeTree.is_entity_exist():
            # 描画処理中にcontextの変更はできないため、タイマーを利用してオペレーターを実行する
            # 新規生成したノードツリーをエディター上で選択するため、スペースのポインタ情報を引数で渡す
            ptr = str(context.space_data.as_pointer())
            bpy.app.timers.register(
                lambda: None if bpy.ops.pcl4.new_line_node_tree(space_node_editor_ptr = ptr) else None,
                first_interval=0.0)
            return False
        
        # 編集対象が空の場合、選択可能なノードツリーがあれば自動的に選択状態にする
        tree = PencilNodeTree.tree_from_context(context)
        if tree is None and PCL4_OT_SelectDefaultTree.get_default_tree() is not None:
            ptr = str(context.space_data.as_pointer())
            bpy.app.timers.register(
                lambda: None if bpy.ops.pcl4.select_default_tree(space_node_editor_ptr = ptr) else None,
                first_interval=0.0)
            return False

        # ノードは存在するものの選択状態のライン/ラインセットが設定されていない場合、選択をリセットする
        do_reset_selecttion = False
        if tree is not None:
            line_node = tree.get_selected_line()
            if line_node is None:
                if len(tree.enumerate_lines()) > 0:
                    do_reset_selecttion = True
            elif line_node.get_selected_lineset() is None and any(x is not None for x in line_node.enumerate_input_nodes()):
                do_reset_selecttion = True
            if do_reset_selecttion:
                tree_ptr = str(tree.as_pointer())
                bpy.app.timers.register(
                    lambda: None if bpy.ops.pcl4.reset_node_selection(tree_ptr=tree_ptr) else None,
                    first_interval=0.0)

        # ラインリスト表示の選択とアクティブノードが異なる場合、ラインリスト表示選択の同期をタイマーにより実行する
        if not do_reset_selecttion and tree is not None and not tree.show_node_panel:
            active_node = tree.nodes.active
            line_node = tree.get_selected_line()
            do_sync = False
            if isinstance(active_node, LineNode):
                do_sync = line_node != active_node
            elif isinstance(active_node, LineSetNode):
                linenodes = tree.enumerate_lines()
                lineset_node = line_node.get_selected_lineset() if line_node is not None else None
                if lineset_node != active_node:
                    for parent in active_node.find_connected_to_nodes():
                        if parent in linenodes:
                            do_sync = True
                            break
            if do_sync:
                tree_ptr = str(tree.as_pointer())
                bpy.app.timers.register(
                    lambda: None if bpy.ops.pcl4.sync_node_selection(tree_ptr=tree_ptr) else None,
                    first_interval=0.0)
        PreviewManager.validate_cache(tree, context)
        return True

    def draw_switch_buttons(self, context, layout):
        tree = PencilNodeTree.tree_from_context(context)
        nodes = tree.get_node_hierarchy_in_panel()
        active_node = context.active_node if isinstance(context.active_node, PencilNodeMixin) else None
        selected_node = active_node if tree.show_node_panel else None
        layout.alignment = "LEFT"
        for i, node in enumerate(nodes):
            op = layout.operator("pcl4.activate_node",
                text=node.name if node is not None else "Line List",
                text_ctxt = Translation.ctxt,
                translate=node is None,
                icon="NONE" if node is not None else "PRESET",
                depress=node == selected_node)
            op.node.set(node)
            op.preferred_parent_node.set(nodes[i - 1] if i > 0 else None)

    def draw(self, context):
        layout = self.layout
        if not pencil4_render_session.get_dll_valid():
            layout.alert = True
            layout.label(text="Add-on install error", icon="ERROR", text_ctxt=Translation.ctxt)
            layout.operator("pcl4.show_preferences", icon="PREFERENCES", text="Show Details", text_ctxt=Translation.ctxt)
            layout.alert = False
            layout.separator(factor=2.0)

        tree = PencilNodeTree.tree_from_context(context)
        if tree is None:
            return
        
        self.draw_switch_buttons(context, layout.row(align=True))

        if PencilNodeTree.show_node_params(context):
            return

        layout.separator(factor=0.25)
        split_p = layout.split(factor=0.1)
        split_p.column()
        split_p = split_p.split(factor=1.0)
        split_p = split_p.split(factor=0.95)

        row = split_p.row()
        row.enabled = tree.is_entity()

        split = row.split(factor=0.92)

        left_col = split.column()
        left_col.template_list(
            "PCL4_UL_LineListView", "",
            tree, "nodes",
            tree, "linelist_selected_index",
            rows=3, maxrows=3)

        row2 = left_col.row(align=True)
        left_col = row2.column()
        left_col.operator("pcl4.line_list_new_item", text="Add", text_ctxt=Translation.ctxt)
        right_col = row2.column()
        right_col.operator("pcl4.line_list_remove_item", text="Remove", text_ctxt=Translation.ctxt)
        right_col.enabled = tree.get_selected_line() is not None

        split = split.split(factor=1.0)
        right_col = split.column()
        right_col.separator(factor=4.0)
        up_button = right_col.operator("pcl4.line_list_move_item", icon="TRIA_UP", text="")
        up_button.button_type = "UP"
        down_button = right_col.operator("pcl4.line_list_move_item", icon="TRIA_DOWN", text="")
        down_button.button_type = "DOWN"

        right_col.enabled = len(tree.enumerate_lines()) >= 2

        split_p = split_p.split(factor=1.0)
        split_p.column()
        layout.separator(factor=0.25)


class PCL4_PT_line(PCL4_PT_PencilLineList_mixin, LineNodePanel.PCL4_PT_line_base, bpy.types.Panel):
    bl_idname = "PCL4_PT_line_parameters_for_linelist"

    @classmethod
    def poll(cls, context):
        return cls.linelist_poll(context) and super().poll(context) and not PencilNodeTree.show_node_params(context)


class PCL4_PT_lineset(PCL4_PT_PencilLineList_mixin, LineNodePanel.PCL4_PT_lineset_base, bpy.types.Panel):
    bl_idname = "PCL4_PT_lineset_for_linelist"

    @classmethod
    def poll(cls, context):
        return cls.linelist_poll(context) and super().poll(context) and not PencilNodeTree.show_node_params(context)


class PCL4_PT_lineset_brush(PCL4_PT_PencilLineList_mixin, LineNodePanel.PCL4_PT_lineset_brush_base, bpy.types.Panel):
    bl_idname = "PCL4_PT_lineset_brush_for_linelist"
    bl_parent_id = "PCL4_PT_lineset_for_linelist"


class PCL4_PT_lineset_edge(PCL4_PT_PencilLineList_mixin, LineNodePanel.PCL4_PT_lineset_edge_base, bpy.types.Panel):
    bl_idname = "PCL4_PT_lineset_edge_for_linelist"
    bl_parent_id = "PCL4_PT_lineset_for_linelist"
 

class PCL4_PT_lineset_reduction(PCL4_PT_PencilLineList_mixin, LineNodePanel.PCL4_PT_lineset_reduction_base, bpy.types.Panel):
    bl_idname = "PCL4_PT_lineset_reduction_for_linelist"
    bl_parent_id = "PCL4_PT_lineset_for_linelist"


class PCL4_OT_LineListNewItemOperator(bpy.types.Operator):
    bl_idname = "pcl4.line_list_new_item"
    bl_label = "New Item"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node_tree = PencilNodeTree.tree_from_context(context)
        for node in node_tree.nodes:
            node.select = False
        lines = node_tree.enumerate_lines()

        new_node = node_tree.nodes.new(type=LineNode.bl_idname)
        location = [0, 0] if len(lines) == 0 else lines[-1].location
        while(next((x for x in lines if abs(x.location[0] - location[0]) < 1 and abs(x.location[1] - location[1]) < 1), None)):
            location = [location[0], location[1] -200]
        new_node.location = location
        new_node.name = LineNode.bl_label
        new_node.select = True
        node_tree.nodes.active = new_node
        node_tree.set_selected_line(new_node)
        return {"FINISHED"}


class PCL4_OT_LineListRemoveItemOperator(bpy.types.Operator):
    bl_idname = "pcl4.line_list_remove_item"
    bl_label = "Remove Item"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        node_tree = PencilNodeTree.tree_from_context(context)
        node_to_remove = node_tree.get_selected_line()
        if node_to_remove is None:
            return {"CANCELLED"}

        lines = node_tree.enumerate_lines()
        index = lines.index(node_to_remove)
        node_to_select = (lines[index + 1] if index < len(lines) - 1 else lines[index - 1]) if len(lines) > 0 else None 

        node_to_remove.delete_if_unused(node_tree)
        node_tree.set_selected_line(node_to_select)

        return {"FINISHED"}


class PCL4_OT_LineListMoveItemOperator(bpy.types.Operator):
    bl_idname = "pcl4.line_list_move_item"
    bl_label = "Move Item"
    bl_options = {"REGISTER", "UNDO"}

    button_type: bpy.props.StringProperty(default="UP")

    def execute(self, context):
        node_tree = PencilNodeTree.tree_from_context(context)
        src_node = node_tree.get_selected_line()

        if src_node is None:
            return {"CANCELLED"}

        ofs = -1 if self.button_type == "UP" else 1 if self.button_type == "DOWN" else 0
        if ofs == 0:
            return {"CANCELLED"}

        lines = node_tree.enumerate_lines()
        src_index = lines.index(src_node)
        tgt_index = src_index + ofs
        if tgt_index < 0 or len(lines) <= tgt_index:
            return {"CANCELLED"}

        tgt_node = lines[tgt_index]
        src_node.render_priority, tgt_node.render_priority = tgt_node.render_priority, src_node.render_priority
        lines[src_index], lines[tgt_index] = tgt_node, src_node

        # render_priorityの設定値が重複している場合、正しく移動できないのでpriorityを再計算する
        # render_priorityは負数を許可していないので別のint配列を作っておく
        priorities = list(x.render_priority for x in lines)
        
        # リストの上方向のpriority計算
        for i in range(min(src_index, tgt_index), -1, -1):
            priorities[i] = min(priorities[i], priorities[i + 1] - 1)
        priorities[0] = max(priorities[0], 0)
        
        # リストの下方向のpriority計算
        for i in range(1, len(lines), 1):
            priorities[i] = max(priorities[i], priorities[i - 1] + 1)
        
        # priorityをプロパティの反映させる
        for i in range(len(lines)):
            if lines[i].render_priority != priorities[i]:
                lines[i].render_priority = priorities[i]

        #
        node_tree.set_selected_line(src_node)

        return {"FINISHED"}


class PCL4_OT_ActivateNode(bpy.types.Operator):
    bl_idname = "pcl4.activate_node"
    bl_label = "Activate Node"
    bl_options = {'REGISTER', 'UNDO'}

    node: bpy.props.PointerProperty(type=NamedRNAStruct)
    preferred_parent_node: bpy.props.PointerProperty(type=NamedRNAStruct)

    def execute(self, context: bpy.context):
        tree = PencilNodeTree.tree_from_context(context)
        if tree is None:
            return {"CANCELLED"}
        tree.nodes.active = self.node.get_node(context)
        tree.preferred_parent_node_in_panel.set(self.preferred_parent_node.get_node(context))
        return {"FINISHED"}

def select_tree(tree, context, space_node_editor_ptr):
    if context.space_data is not None:
        context.space_data.node_tree = tree
    else:
        ptr = int(space_node_editor_ptr)
        for screen in context.blend_data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if ptr == space.as_pointer():
                        space.node_tree = tree

class PCL4_OT_NewLineNodeTree(bpy.types.Operator):
    bl_idname = "pcl4.new_line_node_tree"
    bl_label = "New Line Node Tree"

    space_node_editor_ptr: bpy.props.StringProperty(name='space_node_editor_ptr')

    def execute(self, context):
        tree = context.blend_data.node_groups.new("Pencil+ 4 Line Node Tree", "Pencil4NodeTreeType")
        select_tree(tree, context, self.space_node_editor_ptr)
        return {"FINISHED"}


class PCL4_OT_SelectDefaultTree(bpy.types.Operator):
    bl_idname = "pcl4.select_default_tree"
    bl_label = "Select Default Tree"

    space_node_editor_ptr: bpy.props.StringProperty(name='space_node_editor_ptr')

    @staticmethod
    def get_default_tree():
        return next((x for x in PencilNodeTree.enumerate_entity_trees() if x.use_fake_user or x.users > 0), None)

    def execute(self, context):
        tree = __class__.get_default_tree()
        if tree is None:
            return {"CANCELLED"}
        select_tree(tree, context, self.space_node_editor_ptr)
        return {"FINISHED"}


class PCL4_OT_SyncNodeSelection(bpy.types.Operator):
    bl_idname = "pcl4.sync_node_selection"
    bl_label = "Sync Node Selection"

    tree_ptr: bpy.props.StringProperty(name='tree_ptr')

    def execute(self, context):
        tree_ptr = int(self.tree_ptr)
        tree = next((x for x in bpy.data.node_groups if x.as_pointer() == tree_ptr), None)
        if tree is None:
            return {"CANCELLED"}

        linenodes = tree.enumerate_lines()
        active_node = tree.nodes.active

        if isinstance(active_node, LineNode):
            if active_node in linenodes:
                tree.linelist_selected_index = -1
                tree.set_selected_line(active_node) 
        elif isinstance(active_node, LineSetNode):
            line_node = tree.get_selected_line()
            if line_node and active_node in line_node.enumerate_input_nodes():
                line_node.set_selected_lineset(active_node)
            else:
                for line_node in linenodes:
                    if line_node and active_node in line_node.enumerate_input_nodes():
                        tree.set_selected_line(line_node) 
                        line_node.set_selected_lineset(active_node)
                        break

        for screen in context.blend_data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if getattr(space, "node_tree", None) == tree:
                        area.tag_redraw()

        return {"FINISHED"}
    

class PCL4_OT_ResetNodeSelection(bpy.types.Operator):
    bl_idname = "pcl4.reset_node_selection"
    bl_label = "Reset Node Selection"

    tree_ptr: bpy.props.StringProperty(name='tree_ptr')

    def execute(self, context):
        tree_ptr = int(self.tree_ptr)
        tree = next((x for x in bpy.data.node_groups if x.as_pointer() == tree_ptr), None)
        if tree is None:
            return {"CANCELLED"}

        line_node = tree.get_selected_line()
        if line_node is None:
            lines = tree.enumerate_lines()
            if len(lines) == 0:
                return {"CANCELLED"}
            line_node = lines[0]
            tree.set_selected_line(line_node)

        lineset_node = line_node.get_selected_lineset()
        if lineset_node is None:
            linesets = line_node.enumerate_input_nodes()
            for i, lineset in enumerate(linesets):
                if lineset is not None:
                    line_node.set_selected_lineset(linesets[i])
                    break

        for screen in context.blend_data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if getattr(space, "node_tree", None) == tree:
                        area.tag_redraw()

        return {"FINISHED"}
# ----------------------------------------------------------------------------
# Copyright (c) 2020, Diego Garcia Huerta.
#
# Your use of this software as distributed in this GitHub repository, is
# governed by the Apache License 2.0
#
# Your use of the Shotgun Pipeline Toolkit is governed by the applicable
# license agreement between you and Autodesk / Shotgun.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------


"""
Hook that loads defines all the available actions, broken down by publish type.
"""

import os
from contextlib import contextmanager

import bpy
import sgtk
from sgtk.errors import TankError


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


HookBaseClass = sgtk.get_hook_baseclass()


def get_view3d_operator_context():
    """
    Adapted from several sources, it seems like  io ops needs a
    specific context that if run external to the Blender console needs to
    be specified
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        context_override = {
                            "window": window,
                            "screen": window.screen,
                            "area": area,
                            "region": region,
                            "scene": bpy.context.scene,
                        }
                        return context_override
    return None


@contextmanager
def view3d_operator_context():
    """
    Runs the enclosed operators within a 3D view context, if there is one.
    Passing the override dict to the operator was removed in Blender 4.0.
    """
    context_override = get_view3d_operator_context()
    if context_override is None:
        yield
        return

    with bpy.context.temp_override(**context_override):
        yield


# maps file extensions to the operator that imports them. Most legacy
# `import_scene` / `import_mesh` operators were replaced by `wm.*_import` in
# Blender 4.x, and Collada support was removed in Blender 5.0.
IMPORT_OPERATORS = {
    "abc": ("wm", "alembic_import"),
    "dae": ("wm", "collada_import"),
    "obj": ("wm", "obj_import"),
    "stl": ("wm", "stl_import"),
    "ply": ("wm", "ply_import"),
    "usd": ("wm", "usd_import"),
    "usda": ("wm", "usd_import"),
    "usdc": ("wm", "usd_import"),
    "usdz": ("wm", "usd_import"),
    "fbx": ("import_scene", "fbx"),
    "glb": ("import_scene", "gltf"),
    "gltf": ("import_scene", "gltf"),
    "svg": ("import_curve", "svg"),
    "bvh": ("import_anim", "bvh"),
}


def _find_import_operator(extension_name):
    """
    Returns the operator that can import files with the given extension
    in this version of Blender, or None.
    """
    candidates = []
    if extension_name in IMPORT_OPERATORS:
        candidates.append(IMPORT_OPERATORS[extension_name])

    # legacy lookup, i.e. `bpy.ops.import_scene.<extension>`
    for module_name in ("import_scene", "import_mesh", "import_curve", "import_anim"):
        candidates.append((module_name, extension_name))

    for module_name, operator_name in candidates:
        module = getattr(bpy.ops, module_name, None)
        # `bpy.ops.<module>.<anything>` always returns an operator wrapper,
        # so check that the operator actually exists
        if module is not None and operator_name in dir(module):
            return getattr(module, operator_name)

    return None


def _get_compositor_node_tree(scene):
    """
    Returns the compositor node tree of the scene, creating it if needed.
    Blender 5.0 replaced `scene.node_tree` by `scene.compositing_node_group`.
    """
    if hasattr(scene, "compositing_node_group"):
        if not scene.compositing_node_group:
            scene.compositing_node_group = bpy.data.node_groups.new(
                "Compositor", "CompositorNodeTree"
            )
        return scene.compositing_node_group

    if not scene.node_tree:
        scene.use_nodes = True
    return scene.node_tree


def _get_sequencer_strips(scene):
    """
    Returns the strips collection of the sequence editor, creating it if
    needed. `sequences` was renamed to `strips` in Blender 4.4 and removed in
    Blender 5.0.
    """
    sequence_editor = scene.sequence_editor or scene.sequence_editor_create()
    if hasattr(sequence_editor, "strips"):
        return sequence_editor.strips
    return sequence_editor.sequences


class BlenderActions(HookBaseClass):

    ###########################################################################
    # public interface - to be overridden by deriving classes

    def generate_actions(self, sg_publish_data, actions, ui_area):
        """
        Returns a list of action instances for a particular publish. This
        method is called each time a user clicks a publish somewhere in the UI.
        The data returned from this hook will be used to populate the actions
        menu for a publish.

        The mapping between Publish types and actions are kept in a different
        place (in the configuration) so at the point when this hook is called,
        the loader app has already established *which* actions are appropriate
        for this object.

        The hook should return at least one action for each item passed in via
        the actions parameter.

        This method needs to return detailed data for those actions, in the
        form of a list of dictionaries, each with name, params, caption and
        description keys.

        Because you are operating on a particular publish, you may tailor the
        output  (caption, tooltip etc) to contain custom information suitable
        for this publish.

        The ui_area parameter is a string and indicates where the publish is to
        be shown.
        - If it will be shown in the main browsing area, "main" is passed.
        - If it will be shown in the details area, "details" is passed.
        - If it will be shown in the history area, "history" is passed.

        Please note that it is perfectly possible to create more than one
        action "instance" for an action!
        You can for example do scene introspectionvif the action passed in
        is "character_attachment" you may for examplevscan the scene, figure
        out all the nodes where this object can bevattached and return a list
        of action instances: "attach to left hand",v"attach to right hand" etc.
        In this case, when more than  one object isvreturned for an action, use
        the params key to pass additional data into the run_action hook.

        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        :param actions: List of action strings which have been
                        defined in the app configuration.
        :param ui_area: String denoting the UI Area (see above).
        :returns List of dictionaries, each with keys name, params, caption
         and description
        """

        app = self.parent
        app.log_debug(
            "Generate actions called for UI element %s. "
            "Actions: %s. Publish Data: %s" % (ui_area, actions, sg_publish_data)
        )

        action_instances = []

        if "link" in actions:
            action_instances.append(
                {
                    "name": "link",
                    "params": None,
                    "caption": "Link Library file",
                    "description": (
                        "This will link the contents of the chosen item"
                        " to the current collection."
                    ),
                }
            )

        if "import" in actions:
            action_instances.append(
                {
                    "name": "import",
                    "params": None,
                    "caption": "Import into Collection",
                    "description": (
                        "This will import the item into the current collection."
                    ),
                }
            )

        if "append" in actions:
            action_instances.append(
                {
                    "name": "append",
                    "params": None,
                    "caption": "Append Library File",
                    "description": (
                        "This will add the contents of the chosen item"
                        " to the current collection."
                    ),
                }
            )

        if "asCompositorNodeMovieClip" in actions:
            action_instances.append(
                {
                    "name": "asCompositorNodeMovieClip",
                    "params": None,
                    "caption": "As Compositor Movie Clip",
                    "description": (
                        "This will create a new compositor node and load the movie into it"
                    ),
                }
            )

        if "asCompositorNodeImage" in actions:
            action_instances.append(
                {
                    "name": "asCompositorNodeImage",
                    "params": None,
                    "caption": "As Compositor Image Node",
                    "description": (
                        "This will create a new compositor node and load the image into it"
                    ),
                }
            )

        if "asSequencerImage" in actions:
            action_instances.append(
                {
                    "name": "asSequencerImage",
                    "params": None,
                    "caption": "As Sequencer Image (channel 3)",
                    "description": (
                        "This will create a new sound clip in the sequencer in channel 3"
                    ),
                }
            )

        if "asSequencerMovie" in actions:
            action_instances.append(
                {
                    "name": "asSequencerMovie",
                    "params": None,
                    "caption": "As Sequencer Movie (channel 1)",
                    "description": (
                        "This will create a new sound clip in the sequencer in channel 1"
                    ),
                }
            )

        if "asSequencerSound" in actions:
            action_instances.append(
                {
                    "name": "asSequencerSound",
                    "params": None,
                    "caption": "As Sequencer Sound (channel 2)",
                    "description": (
                        "This will create a new sound clip in the sequencer in channel 2"
                    ),
                }
            )

        return action_instances

    def execute_multiple_actions(self, actions):
        """
        Executes the specified action on a list of items.

        The default implementation dispatches each item from ``actions`` to
        the ``execute_action`` method.

        The ``actions`` is a list of dictionaries holding all the actions to
        execute.
        Each entry will have the following values:

            name: Name of the action to execute
            sg_publish_data: Publish information coming from Shotgun
            params: Parameters passed down from the generate_actions hook.

        .. note::
            This is the default entry point for the hook. It reuses the
            ``execute_action`` method for backward compatibility with hooks
             written for the previous version of the loader.

        .. note::
            The hook will stop applying the actions on the selection if an
            error is raised midway through.

        :param list actions: Action dictionaries.
        """
        app = self.parent
        for single_action in actions:
            app.log_debug("Single Action: %s" % single_action)
            name = single_action["name"]
            sg_publish_data = single_action["sg_publish_data"]
            params = single_action["params"]

            self.execute_action(name, params, sg_publish_data)

    def execute_action(self, name, params, sg_publish_data):
        """
        Execute a given action. The data sent to this be method will
        represent one of the actions enumerated by the generate_actions method.

        :param name: Action name string representing one of the items returned
                     by generate_actions.
        :param params: Params data, as specified by generate_actions.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        :returns: No return value expected.
        """
        app = self.parent
        app.log_debug(
            "Execute action called for action %s. "
            "Parameters: %s. Publish Data: %s" % (name, params, sg_publish_data)
        )

        # resolve path
        # toolkit uses utf-8 encoded strings internally and Blender API
        # expects unicode so convert the path to ensure filenames containing
        # complex characters are supported
        path = self.get_publish_path(sg_publish_data).replace(os.path.sep, "/")

        if name == "link":
            self._create_link(path, sg_publish_data)

        if name == "append":
            self._create_append(path, sg_publish_data)

        if name == "import":
            self._do_import(path, sg_publish_data)

        if name == "asCompositorNodeMovieClip":
            self._create_compositor_node_movie_clip(path, sg_publish_data)

        if name == "asCompositorNodeImage":
            self._create_compositor_node_image(path, sg_publish_data)

        if name == "asSequencerImage":
            self._create_sequencer_image(path, sg_publish_data)

        if name == "asSequencerMovie":
            self._create_sequencer_movie(path, sg_publish_data)

        if name == "asSequencerSound":
            self._create_sequencer_sound(path, sg_publish_data)

    ###########################################################################
    # helper methods which can be subclassed in custom hooks to fine tune the
    # behaviour of things

    def _create_link(self, path, sg_publish_data):
        """
        Create a reference with the same settings Blender would use
        if you used the create settings dialog.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """
        if not os.path.exists(path):
            raise TankError("File not found on disk - '%s'" % path)

        with bpy.data.libraries.load(path, link=True) as (data_from, data_to):
            data_to.collections = data_from.collections

        for collection in data_to.collections:
            new_collection = bpy.data.objects.new(collection.name, None)
            new_collection.instance_type = "COLLECTION"
            new_collection.instance_collection = collection
            bpy.context.scene.collection.objects.link(new_collection)

    def _create_append(self, path, sg_publish_data):
        """
        Create a reference with the same settings Blender would use
        if you used the create settings dialog.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """
        if not os.path.exists(path):
            raise TankError("File not found on disk - '%s'" % path)

        with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
            data_to.collections = data_from.collections

        for collection in data_to.collections:
            new_collection = bpy.data.objects.new(collection.name, None)
            new_collection.instance_type = "COLLECTION"
            new_collection.instance_collection = collection
            bpy.context.scene.collection.objects.link(new_collection)

    def _do_import(self, path, sg_publish_data):
        """
        Create a reference with the same settings Blender would use
        if you used the create settings dialog.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """
        if not os.path.exists(path):
            raise TankError("File not found on disk - '%s'" % path)

        _, extension = os.path.splitext(path)

        extension_name = extension.lower()[1:]

        importer = _find_import_operator(extension_name)
        if importer is None:
            raise TankError(
                "File extension not supported %s - '%s'" % (extension_name, path)
            )

        kwargs = {"filepath": path}
        if "as_background_job" in importer.get_rna_type().properties.keys():
            kwargs["as_background_job"] = False

        with view3d_operator_context():
            importer(**kwargs)

    def _create_compositor_node_movie_clip(self, path, sg_publish_data):
        """
        Create a new clip compositor node and load the selected publish into it.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """
        node_tree = _get_compositor_node_tree(bpy.context.scene)
        node = node_tree.nodes.new("CompositorNodeMovieClip")
        node.clip = bpy.data.movieclips.load(path, check_existing=True)

    def _create_compositor_node_image(self, path, sg_publish_data):
        """
        Create a new image compositor node and load the selected publish into it.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """

        node_tree = _get_compositor_node_tree(bpy.context.scene)
        node = node_tree.nodes.new("CompositorNodeImage")
        node.image = bpy.data.images.load(path, check_existing=True)

    def _create_sequencer_sound(self, path, sg_publish_data):
        """
        Create a new sound for the sequence editor and load the selected publish into it.
        Note we always use channel 2

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """

        filename_path, filename_file = os.path.split(path)
        _get_sequencer_strips(bpy.context.scene).new_sound(
            filename_file,
            filepath=path,
            channel=2,
            frame_start=bpy.context.scene.frame_current,
        )

    def _create_sequencer_movie(self, path, sg_publish_data):
        """
        Create a new movie for the sequence editor and load the selected publish into it.
        Note we always use channel 1

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """

        filename_path, filename_file = os.path.split(path)
        _get_sequencer_strips(bpy.context.scene).new_movie(
            filename_file,
            filepath=path,
            channel=1,
            frame_start=bpy.context.scene.frame_current,
        )

    def _create_sequencer_image(self, path, sg_publish_data):
        """
        Create a new image for the sequence editor and load the selected publish into it.
        Note we always use channel 3

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard
                                publish fields.
        """

        filename_path, filename_file = os.path.split(path)
        _get_sequencer_strips(bpy.context.scene).new_image(
            filename_file,
            filepath=path,
            channel=3,
            frame_start=bpy.context.scene.frame_current,
        )

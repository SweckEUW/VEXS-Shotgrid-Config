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


import os
import sgtk

from tank_vendor import six
from sgtk.util.filesystem import ensure_folder_exists

import bpy

HookBaseClass = sgtk.get_hook_baseclass()

# Export operator (bpy.ops module, operator name) and publish type per format.
# The publish types match the action mappings of the Blender loader.
GEOMETRY_EXPORTERS = {
    "abc": {"operator": ("wm", "alembic_export"), "publish_type": "Alembic Cache"},
    "fbx": {"operator": ("export_scene", "fbx"), "publish_type": "FBX File"},
    "glb": {"operator": ("export_scene", "gltf"), "publish_type": "Glb File"},
}


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


class BlenderSessionGeometryPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open blender session.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    """

    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """
        <p>This plugin publishes session geometry for the current session. Any
        session geometry will be exported as Alembic, FBX or glTF Binary
        (configured "Export Format" setting) to the path defined by this
        plugin's configured "Publish Template" setting. The item is not
        offered if the exporter is not available in this Blender.</p>
        """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        # inherit the settings from the base publish plugin
        base_settings = super(BlenderSessionGeometryPublishPlugin, self).settings or {}

        # settings specific to this class
        blender_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                "correspond to a template defined in "
                "templates.yml.",
            },
            "Export Format": {
                "type": "str",
                "default": "abc",
                "description": "Geometry format to export: abc, fbx or glb. "
                "Only the collected item of this format is accepted.",
            },
            "Checked": {
                "type": "bool",
                "default": True,
                "description": "Whether the item is checked in the publisher "
                "by default.",
            },
        }

        # update the base settings
        base_settings.update(blender_publish_settings)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["blender.*", "file.blender"]
        """
        return ["blender.session.geometry.*"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # every configured instance of this plugin only handles its own format,
        # return before touching the item so the other instances keep theirs
        geometry_format = settings["Export Format"].value
        if item.properties.get("geometry_format") != geometry_format:
            return {"accepted": False}

        if geometry_format not in GEOMETRY_EXPORTERS:
            self.logger.warning(
                "Unknown geometry export format '%s'. Not accepting the item."
                % geometry_format
            )
            return {"accepted": False}

        accepted = True
        publisher = self.parent
        template_name = settings["Publish Template"].value

        # ensure a work file template is available on the parent item
        work_template = item.parent.properties.get("work_template")
        if not work_template:
            self.logger.debug(
                "A work template is required for the session item in order to "
                "publish session geometry. Not accepting session geom item."
            )
            accepted = False

        # ensure the publish template is defined and valid and that we also have
        publish_template = publisher.get_template_by_name(template_name)
        if not publish_template:
            self.logger.debug(
                "The valid publish template could not be determined for the "
                "session geometry item. Not accepting the item."
            )
            accepted = False

        # we've validated the publish template. add it to the item properties
        # for use in subsequent methods
        item.properties["publish_template"] = publish_template

        # check that the export command is available!
        alembic_missing = geometry_format == "abc" and not bpy.app.build_options.alembic
        if alembic_missing or _get_export_operator(geometry_format) is None:
            self.logger.debug(
                "Item not accepted because the %s export command "
                "is not available in this version of Blender" % geometry_format
            )
            accepted = False

        # because a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        item.context_change_allowed = False

        return {"accepted": accepted, "checked": settings["Checked"].value}

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        path = _session_path()

        # ---- ensure the session has been saved

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            error_msg = "The Blender session has not been saved."
            self.logger.error(error_msg, extra=_get_save_as_action())
            raise Exception(error_msg)

        # get the normalized path
        path = sgtk.util.ShotgunPath.normalize(path)

        # check that there is still geometry in the scene:
        if not bpy.data.meshes:
            error_msg = (
                "Validation failed because there is no geometry in the scene "
                "to be exported. You can uncheck this plugin or create "
                "geometry to export to avoid this error."
            )
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # get the configured work file template
        work_template = item.parent.properties.get("work_template")
        publish_template = item.properties.get("publish_template")

        # get the current scene path and extract fields from it using the work
        # template:
        work_fields = work_template.get_fields(path)

        # ensure the fields work for the publish template
        missing_keys = publish_template.missing_keys(work_fields)
        if missing_keys:
            error_msg = (
                "Work file '%s' missing keys required for the "
                "publish template: %s" % (path, missing_keys)
            )
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # create the publish path by applying the fields. store it in the item's
        # properties. This is the path we'll create and then publish in the base
        # publish plugin. Also set the publish_path to be explicit.
        item.properties["path"] = publish_template.apply_fields(work_fields)
        item.properties["publish_path"] = item.properties["path"]

        # use the work file's version number when publishing
        if "version" in work_fields:
            item.properties["publish_version"] = work_fields["version"]

        # set explicitly, the extension lookup of the base plugin would
        # register .fbx as "Motion Builder FBX"
        geometry_format = settings["Export Format"].value
        item.properties["publish_type"] = GEOMETRY_EXPORTERS[geometry_format]["publish_type"]

        # run the base class validation
        return super(BlenderSessionGeometryPublishPlugin, self).validate(settings, item)

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # get the path to create and publish
        publish_path = item.properties["path"]

        # ensure the publish folder exists:
        publish_folder = os.path.dirname(publish_path)
        self.parent.ensure_folder_exists(publish_folder)

        geometry_format = settings["Export Format"].value

        try:
            context = get_view3d_operator_context()
            exporter = _get_export_operator(geometry_format)

            export_args = _get_export_args(geometry_format, publish_path)
            # only pass the options this Blender version knows about
            # (e.g. `renderable_only` was removed in Blender 5.0)
            supported_args = exporter.get_rna_type().properties.keys()
            export_args = {
                key: value
                for key, value in export_args.items()
                if key in supported_args
            }

            # passing the override dict to the operator was removed in 4.0
            if context:
                with bpy.context.temp_override(**context):
                    exporter(**export_args)
            else:
                exporter(**export_args)

        except Exception as e:
            error_msg = "Failed to export Geometry: %s" % e
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # Now that the path has been generated, hand it off to the
        super(BlenderSessionGeometryPublishPlugin, self).publish(settings, item)


def _get_export_operator(geometry_format):
    """
    Returns the export operator for the given format in this version of
    Blender, or None.
    """
    module_name, operator_name = GEOMETRY_EXPORTERS[geometry_format]["operator"]
    module = getattr(bpy.ops, module_name, None)
    # `bpy.ops.<module>.<anything>` always returns an operator wrapper,
    # so check that the operator actually exists
    if module is not None and operator_name in dir(module):
        return getattr(module, operator_name)
    return None


def _get_export_args(geometry_format, publish_path):
    """
    Returns the export operator options for the given format.
    """
    if geometry_format == "abc":
        start_frame, end_frame = _find_scene_animation_range()
        return {
            "filepath": publish_path,
            "selected": False,
            "renderable_only": True,
            "uvs": True,
            "face_sets": True,
            "start": start_frame,
            "end": end_frame,
            "as_background_job": False,
        }

    if geometry_format == "fbx":
        # embed the textures so the file works on its own, e.g. on the VEXS server
        return {
            "filepath": publish_path,
            "use_selection": False,
            "path_mode": "COPY",
            "embed_textures": True,
        }

    # glb packs geometry, materials and textures into one binary file
    return {
        "filepath": publish_path,
        "export_format": "GLB",
        "use_selection": False,
        "export_apply": True,
    }


def _find_scene_animation_range():
    """
    Find the animation range from the current scene.
    """

    actions = [action.frame_range for action in bpy.data.actions]
    keys = sorted(set([key for action in actions for key in action]))

    if not keys:
        start, end = 1, 1
    else:
        start, end = keys[0], keys[-1]

    return start, end


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    path = bpy.data.filepath
    return path


def _save_session(path):
    """
    Save the current session to the supplied path.
    """

    # Ensure that the folder is created when saving
    folder = os.path.dirname(path)
    ensure_folder_exists(folder)

    bpy.ops.wm.save_mainfile(filepath=path)


# TODO: method duplicated in all the blender hooks
def _get_save_as_action():
    """
    Simple helper for returning a log action dict for saving the session
    """

    engine = sgtk.platform.current_engine()

    callback = _save_as

    # if workfiles2 is configured, use that for file save
    if "tk-multi-workfiles2" in engine.apps:
        app = engine.apps["tk-multi-workfiles2"]
        if hasattr(app, "show_file_save_dlg"):
            callback = app.show_file_save_dlg

    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current session",
            "callback": callback,
        }
    }


def _save_as():
    bpy.ops.wm.save_mainfile("INVOKE_AREA")

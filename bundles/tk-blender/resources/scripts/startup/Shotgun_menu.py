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
#
# VEXS changes (Blender 4.2+ / 5.x):
#   - PySide6 support (falls back to PySide2)
#   - Qt event loop driven by a persistent bpy.app.timers callback instead of
#     a modal operator (modal handlers are lost when a file is loaded)
#   - toolkit bootstrap deferred to a timer, so it works when the script is
#     passed via `-P` instead of being installed as a startup script
#   - top bar entry added via TOPBAR_MT_editor_menus.append() instead of
#     rewriting Blender's menu source code through the `ast` module
#   - `imp` replaced by `importlib` (removed in Python 3.12)
# ----------------------------------------------------------------------------


import os
import sys
import site
import importlib.util

import bpy


DIR_PATH = os.path.dirname(os.path.abspath(__file__))

ext_libs = os.environ.get("PYSIDE2_PYTHONPATH")

if ext_libs and os.path.exists(ext_libs):
    if ext_libs not in sys.path:
        print("Added path: %s" % ext_libs)
        site.addsitedir(ext_libs)

bl_info = {
    "name": "ShotGrid Bridge Plugin",
    "description": "ShotGrid Toolkit Engine for Blender",
    "author": "Diego Garcia Huerta",
    "license": "GPL",
    "deps": "",
    "version": (1, 1, 1),
    "blender": (4, 2, 0),
    "location": "ShotGrid",
    "warning": "",
    "wiki_url": "https://github.com/diegogarciahuerta/tk-blender/releases",
    "tracker_url": "https://github.com/diegogarciahuerta/tk-blender/issues",
    "link": "https://github.com/diegogarciahuerta/tk-blender",
    "support": "COMMUNITY",
    "category": "User Interface",
}


PYSIDE_MISSING_MESSAGE = (
    "\n"
    + "-" * 80
    + "\nCould not import PySide6 (or PySide2) as a Python module. "
    + "ShotGrid menu will not be available."
    + "\n\nInstall PySide6-Essentials (< 6.11) into Blender's Python or point the "
    + "PYSIDE2_PYTHONPATH environment variable to a folder containing it.\n"
    + "-" * 80
)

try:
    from PySide6 import QtWidgets

    PYSIDE_IMPORTED = True
except ImportError:
    try:
        from PySide2 import QtWidgets

        PYSIDE_IMPORTED = True
    except ImportError:
        PYSIDE_IMPORTED = False


# interval in seconds in which Blender hands control over to Qt
QT_EVENT_LOOP_INTERVAL = 0.01


def _main_window():
    """
    Returns the first Blender window, or None if there is none (background
    mode or Blender is shutting down).
    """
    wm = bpy.context.window_manager
    if wm and wm.windows:
        return wm.windows[0]
    return None


def _run_with_window_context(callback):
    """
    Runs the callback with a valid window in the context.

    Timers run without a window in the context, but many operators that the
    toolkit apps trigger (open/save files, file browsers, ...) need one.
    """
    window = _main_window()
    if window is None:
        return callback()

    with bpy.context.temp_override(window=window):
        return callback()


def _process_qt_events():
    """
    Persistent timer that keeps the Qt event loop alive inside Blender.
    """
    app = QtWidgets.QApplication.instance()
    if app:
        _run_with_window_context(app.processEvents)
        app.sendPostedEvents(None, 0)
    return QT_EVENT_LOOP_INTERVAL


def start_qt_event_loop():
    """
    Creates the QApplication if needed and starts processing its events.
    """
    if not QtWidgets.QApplication.instance():
        QtWidgets.QApplication(sys.argv)

    if not bpy.app.timers.is_registered(_process_qt_events):
        bpy.app.timers.register(_process_qt_events, persistent=True)


class ShotgunConsoleLog(bpy.types.Operator):
    """
    A simple operator to log issues to the console.
    """

    bl_idname = "shotgun.logger"
    bl_label = "ShotGrid Logger"

    message: bpy.props.StringProperty(name="message", description="message", default="")

    level: bpy.props.StringProperty(name="level", description="level", default="INFO")

    def execute(self, context):
        self.report({self.level}, self.message)
        return {"FINISHED"}


class ShotgunShowMenu(bpy.types.Operator):
    """
    Shows the ShotGrid menu of the current engine
    """

    bl_idname = "shotgun.show_menu"
    bl_label = "ShotGrid"

    def execute(self, context):
        import sgtk

        engine = sgtk.platform.current_engine()
        if engine:
            engine.display_menu()
        else:
            self.report({"WARNING"}, "ShotGrid engine is not running.")
        return {"FINISHED"}


def draw_shotgun_menu(self, context):
    """
    Adds the ShotGrid entry to Blender's top bar.
    """
    self.layout.operator(ShotgunShowMenu.bl_idname, text="ShotGrid", emboss=False)


def boostrap():
    # start the engine
    SGTK_MODULE_PATH = os.environ.get("SGTK_MODULE_PATH")
    if SGTK_MODULE_PATH and SGTK_MODULE_PATH not in sys.path:
        sys.path.insert(0, SGTK_MODULE_PATH)

    engine_startup_path = os.environ.get("SGTK_BLENDER_ENGINE_STARTUP")
    if not engine_startup_path:
        print("ShotGrid: SGTK_BLENDER_ENGINE_STARTUP is not set, toolkit not started.")
        return

    spec = importlib.util.spec_from_file_location(
        "sgtk_blender_engine_startup", engine_startup_path
    )
    engine_startup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine_startup)

    # Fire up Toolkit and the environment engine.
    engine_startup.start_toolkit()


def startup():
    start_qt_event_loop()
    _run_with_window_context(boostrap)
    # run once
    return None


def error_importing_pyside():
    print(PYSIDE_MISSING_MESSAGE)
    _run_with_window_context(
        lambda: bpy.ops.shotgun.logger(level="ERROR", message=PYSIDE_MISSING_MESSAGE)
    )
    # run once
    return None


def register():
    bpy.utils.register_class(ShotgunConsoleLog)

    if not PYSIDE_IMPORTED:
        bpy.app.timers.register(error_importing_pyside, first_interval=1.0)
        return

    bpy.utils.register_class(ShotgunShowMenu)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_shotgun_menu)

    # Blender has to be fully up (windows created) before toolkit can start
    bpy.app.timers.register(startup, first_interval=0.1)


def unregister():
    bpy.utils.unregister_class(ShotgunConsoleLog)

    if not PYSIDE_IMPORTED:
        return

    if bpy.app.timers.is_registered(_process_qt_events):
        bpy.app.timers.unregister(_process_qt_events)

    bpy.types.TOPBAR_MT_editor_menus.remove(draw_shotgun_menu)
    bpy.utils.unregister_class(ShotgunShowMenu)


# the launcher passes this file to Blender using the `-P` argument
if __name__ == "__main__":
    register()

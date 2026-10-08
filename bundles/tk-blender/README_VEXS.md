# tk-blender (VEXS)

Diese Engine ist die Community-Engine
[diegogarciahuerta/tk-blender](https://github.com/diegogarciahuerta/tk-blender) in Version **v1.1.1**
(Apache License 2.0, siehe `LICENSE`). Wir liefern sie direkt mit der Config aus und haben sie für
**Blender 4.2+ / 5.x** angepasst. Eingebunden wird sie in `env/includes/engine_locations.yml` über
einen `path`-Descriptor (`{CONFIG_FOLDER}/bundles/tk-blender`). Die Clients brauchen deshalb kein Git.

Getestet wurde mit Blender 5.0 unter Windows 10.

## Einrichtung

### 1. Software-Entity in ShotGrid
Unter *Admin → Software* einen neuen Eintrag anlegen:

| Feld | Wert |
|---|---|
| Software Name | `Blender` |
| Engine | `tk-blender` |
| Windows Path | leer lassen, dann wird Blender automatisch gefunden, oder z. B. `C:\Program Files\Blender Foundation\Blender 5.0\blender.exe` |

Die automatische Suche findet `C:\Program Files\Blender Foundation\Blender <version>\blender.exe` und
`$BLENDER_BIN_DIR\blender.exe`. Versionen unter 4.2 werden ignoriert.

### 2. PySide6 (Qt für Python)
Die ShotGrid-Oberfläche läuft mit Qt. Blender bringt Qt nicht mit. PySide6 liegt deshalb zentral
im geteilten Google-Drive-Ordner:

```
G:\Meine Ablage\Uni\TH OWL\Semester 6\Bachelorarbeit\VEXS\VEXS-Daten\PySide6
```

Der Pfad steht in `env/includes/software_paths.yml` (`path.windows.blender_pyside`). Die Engine
reicht ihn beim Start über das Setting `pyside_python_path` an Blender weiter. Auf den Clients muss
nichts installiert werden, solange Google Drive dort unter `G:` mit derselben Ordnerstruktur
verfügbar ist. Sonst den Pfad in `software_paths.yml` anpassen oder pro Rechner die
Umgebungsvariable `PYSIDE2_PYTHONPATH` setzen. Die Variable hat Vorrang vor der Config.

> **Wichtig: Nur PySide6 < 6.11 verwenden.** Blender liefert eine ältere MSVC-Runtime
> (`MSVCP140.dll` 14.29) mit. PySide6 ab 6.11 stürzt damit beim Import ab
> (`EXCEPTION_ACCESS_VIOLATION`). Installiert und getestet ist 6.10.2.

So wurde der Ordner erstellt, für eine Neuinstallation:
```bat
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install --no-compile --target "G:\Meine Ablage\Uni\TH OWL\Semester 6\Bachelorarbeit\VEXS\VEXS-Daten\PySide6" "PySide6-Essentials==6.10.2"
```
PySide6 ist abi3-kompatibel. Der Ordner funktioniert daher für alle Blender-Versionen mit
Python 3.9 oder neuer.

Wird PySide6 nicht gefunden, startet Blender trotzdem. Es gibt dann aber kein ShotGrid-Menü, und in
der Konsole steht ein entsprechender Hinweis.

### 3. Starten
Blender aus *Flow Production Tracking Desktop* oder über die Web-App starten. In der Top-Bar
erscheint dann hinter dem Help-Menü der Eintrag **ShotGrid**.

## Optionale Umgebungsvariablen

| Variable | Zweck |
|---|---|
| `BLENDER_BIN_DIR` | Ordner mit `blender.exe`, falls Blender nicht im Standardpfad liegt |
| `SGTK_BLENDER_CMD_EXTRA_ARGS` | zusätzliche Kommandozeilenargumente für Blender, z. B. `--debug-python` |
| `PYSIDE2_PYTHONPATH` | Ordner mit PySide6. Überschreibt `path.windows.blender_pyside` (siehe oben). |

## Was ist konfiguriert

- Environments: `project`, `asset`, `asset_step`, `sequence`, `shot`, `shot_step` (`env/includes/settings/tk-blender.yml`)
- Startet man Blender im Projekt-, Asset-, Sequence- oder Shot-Kontext, öffnet sich automatisch
  „File Open...“. Das läuft über das Engine-Setting `run_at_startup`, weil das
  `launch_at_startup`-Setting von Workfiles2 nur für Maya, Nuke und 3ds Max funktioniert.
- Apps im Step-Kontext: Workfiles2, Snapshot, Publish2, Loader2, Breakdown (Legacy), Shotgun Panel, Python Console, Screening Room, Set Frame Range (nur Shot)
- Templates (`core/templates.yml`):
  - `blender_{asset,shot}_{work,snapshot,publish}`
  - `{asset,shot}_{work,publish}_area_blender`

  Beispiel: `assets/Prop/chair/model/work/blender/scene.v001.blend`
- Publish: Die `.blend`-Datei wird als *Blender Project File* veröffentlicht. Im Asset-Step kommt
  zusätzlich ein Alembic-Cache dazu (`asset_alembic_cache`).
- Loader: `.blend` per Link/Append. Import von Alembic, FBX, USD, OBJ, STL, PLY, glTF, SVG und BVH.
  Bilder, Movies und Sounds landen im Sequencer bzw. im Compositor.

## Änderungen gegenüber v1.1.1 (VEXS-Patches)

- `resources/scripts/startup/Shotgun_menu.py`
  - PySide6-Support mit Fallback auf PySide2
  - Die Qt-Eventloop läuft über einen persistenten `bpy.app.timers`-Callback statt über einen
    Modal-Operator, der beim Laden von Dateien verloren ging.
  - Der Bootstrap passiert per Timer.
  - Der Menü-Eintrag wird über `TOPBAR_MT_editor_menus.append()` eingehängt statt über den
    `ast`-Hack.
  - `imp` ist durch `importlib` ersetzt.
- `startup.py`
  - `BLENDER_USER_SCRIPTS` wird **nicht** mehr überschrieben, dadurch bleiben die User-Add-ons
    erhalten. Das Startup-Skript wird über `-P "<pfad>"` übergeben, mit Quotes wegen Leerzeichen
    im Pfad.
  - `SHOTGUN_SKIP_QTWEBENGINEWIDGETS_IMPORT=1` wird gesetzt.
  - Die Mindestversion ist 4.2, außerdem wurde `linux2` zu `linux` korrigiert.
- `engine.py`
  - Der Versionsvergleich nutzt jetzt Tupel statt `float`.
  - `QTextCodec` ist nur noch optional.
  - Ein Bug beim Entfernen der Load/Save-Handler ist behoben.
  - Eine QApplication wird bei Bedarf erzeugt.
- `info.yml`: `compatibility_dialog_min_version` steht auf 6, sodass unter 4.x/5.x kein
  Warndialog mehr erscheint.
- `hooks/tk-multi-loader2/tk-blender_actions.py`
  - `context.temp_override()` statt Override-Dicts, die seit 4.0 entfernt sind
  - neue `wm.*_import`-Operatoren
  - Compositor über `scene.compositing_node_group` (5.0) und Sequencer über `strips` (4.4+/5.0)
  - Clips und Bilder werden über `bpy.data.*.load()` geladen.
  - Defekte Aufrufe aus dem Original sind entfernt.
- `hooks/tk-multi-publish2/basic/publish_session_geometry.py`
  - Der Alembic-Export läuft über `temp_override`.
  - Es werden nur noch Optionen übergeben, die die jeweilige Blender-Version kennt
    (`renderable_only` gibt es in 5.0 nicht mehr).
- `hooks/thumbnail.py`: Screenshot über `QScreen.grabWindow` (Qt6)
- `hooks/tk-multi-workfiles2/scene_operation_tk-blender.py`: Das `print(**kwargs)`, das einen
  TypeError auslösen konnte, ist durch Logging ersetzt.
- `python/tk_blender/menu_generation.py`
  - Tooltip-Methoden korrigiert (`setToolTip`/`setStatusTip`)
  - „Jump to File System“ läuft über `QDesktopServices`.

## Bekannte Einschränkungen

- Collada (`.dae`) gibt es in Blender 5.0 nicht mehr und kann daher nicht importiert werden.
- Für Shots ist kein Alembic-Publish konfiguriert, weil es kein Shot-Alembic-Template gibt.
- Das Shotgun Panel bietet nur die generischen Aktionen und keine Blender-Loader-Aktionen.
- Die Engine ist ein Community-Projekt und nicht offiziell von Autodesk unterstützt.

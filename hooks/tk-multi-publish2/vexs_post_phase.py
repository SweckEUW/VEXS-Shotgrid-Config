from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

VEXS_URL: str = os.environ.get("VEXS_SERVER_URL", "http://127.0.0.1:8000")
VEXS_EXECUTION_MODE: str = os.environ.get("VEXS_EXECUTION_MODE", "local")  # "local" oder "deadline"
VEXS_TIMEOUT: float = float(os.environ.get("VEXS_TIMEOUT", "30"))  # lokal laufen die Graphen synchron im Request
HOOK_ID_ASSET_PUBLISHED: int = 1  # "Asset Version Published" im VEXS-Backend
OUTPUT_TEMPLATE: str = "asset_vexs_output_area"  # aus core/templates.yml


class VexsPostPhaseHook(HookBaseClass):
    """Meldet einen abgeschlossenen Asset-Publish an den VEXS-Server.
    Enthält bewusst keine Ablauflogik."""

    def post_finalize(self, publish_tree: Any) -> None:
        context = self.parent.context

        # Nur Publishes im Kontext eines Assets melden
        if not context.entity or context.entity["type"] != "Asset":
            return

        # Pro erzeugtem PublishedFile einen eigenen Hook-Call
        for item in publish_tree:
            sg_data: dict[str, Any] | None = item.properties.get("sg_publish_data")
            if not sg_data:
                continue

            publish_path = self._get_publish_path(item, sg_data)
            # Task, mit dem das PublishedFile verknüpft wurde, sonst der aus dem Kontext
            task: dict[str, Any] | None = sg_data.get("task") or context.task
            inputs: dict[str, str | int | None] = {
                "asset_file": publish_path,
                "asset_name": context.entity.get("name"),
                "project_name": context.project.get("name"),
                "artist_name": context.user.get("name") if context.user else None,
                "version": sg_data.get("version_number"),
                "output_dir": self._get_output_dir(publish_path),
                "shotgrid_task_id": task["id"] if task else None,
            }
            self._execute_hook(inputs)

    def _get_publish_path(self, item: Any, sg_data: dict[str, Any]) -> str | None:
        # Nicht item.properties["path"]: das ist beim Session-Publish die Workfile
        sg_path: dict[str, Any] = sg_data.get("path") or {}
        return sg_path.get("local_path") or item.properties.get("publish_path")

    def _get_output_dir(self, publish_path: str | None) -> str | None:
        # Ordner im SG-Dateisystem, {name} und {version} kommen aus dem Pfad der gepublishten Datei,
        # {vexs_format} aus der Endung, damit sich .blend/.abc/.fbx/.glb nicht gegenseitig überschreiben
        tk = self.parent.sgtk
        template = tk.templates.get(OUTPUT_TEMPLATE)
        if not template:
            self.logger.warning(f"VEXS: Template '{OUTPUT_TEMPLATE}' nicht gefunden")
            return None
        if not publish_path:
            return None

        try:
            fields = self.parent.context.as_template_fields(template)
            publish_template = tk.template_from_path(publish_path)
            if publish_template:
                fields.update(publish_template.get_fields(publish_path))
            fields["vexs_format"] = os.path.splitext(publish_path)[1].lstrip(".").lower()
            return template.apply_fields(fields)
        except Exception as exc:
            self.logger.warning(f"VEXS: output_dir nicht ermittelbar: {exc}")
            return None

    def _execute_hook(self, inputs: dict[str, str | int | None]) -> None:
        # None würde den Default im Graph überschreiben, fehlende Werte daher weglassen
        inputs = {name: value for name, value in inputs.items() if value is not None}

        query = urllib.parse.urlencode({"mode": VEXS_EXECUTION_MODE})
        url = f"{VEXS_URL}/api/v1/vexshooks/{HOOK_ID_ASSET_PUBLISHED}/execute?{query}"
        request = urllib.request.Request(
            url,
            data=json.dumps({"inputs": inputs}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # Ein Fehler bei VEXS darf den Publish des Artists nie abbrechen
        try:
            with urllib.request.urlopen(request, timeout=VEXS_TIMEOUT) as response:
                body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self.logger.warning(f"VEXS-Aufruf fehlgeschlagen: {exc}")
            return

        self.logger.info(f"VEXS benachrichtigt ({inputs.get('asset_file')}).")

        # Fehler einzelner Graphen sichtbar machen, ohne den Publish abzubrechen
        for result in body.get("results", []):
            if result.get("error"):
                self.logger.warning(f"VEXS-Graph '{result.get('graph_name')}' fehlgeschlagen: {result['error']}")

import json
import os
import urllib.request
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

VEXS_URL = os.environ.get("VEXS_SERVER_URL", "http://vexs-server:8000")
HOOK_ID_ASSET_PUBLISHED = 1  # "Asset Version Published" im VEXS-Backend


class VexsPostPhaseHook(HookBaseClass):
    """Meldet einen abgeschlossenen Asset-Publish an den VEXS-Server.
    Enthält bewusst keine Ablauflogik."""

    def post_finalize(self, publish_tree):
        context = self.parent.context

        # Nur Publishes im Kontext eines Assets melden
        if not context.entity or context.entity["type"] != "Asset":
            return

        # IDs der in diesem Publish erzeugten PublishedFiles sammeln
        published_file_ids = [
            item.properties["sg_publish_data"]["id"]
            for item in publish_tree
            if item.properties.get("sg_publish_data")
        ]
        if not published_file_ids:
            return

        payload = {
            "project_id": context.project["id"],
            "entity": {"type": "Asset", "id": context.entity["id"]},
            "task_id": context.task["id"] if context.task else None,
            "user_id": context.user["id"] if context.user else None,
            "published_file_ids": published_file_ids,
        }

        url = f"{VEXS_URL}/api/v1/vexshooks/{HOOK_ID_ASSET_PUBLISHED}/execute"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # Ein Fehler bei VEXS darf den Publish des Artists nie abbrechen
        try:
            urllib.request.urlopen(request, timeout=3)
            self.logger.info("VEXS benachrichtigt.")
        except Exception as exc:
            self.logger.warning(f"VEXS nicht erreichbar: {exc}")
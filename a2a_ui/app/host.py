"""
Host bridge module for the a2a_ui application.

This module exposes a ``HostBridge`` class that proxies all UI requests to a
running HostAgent service.  In the UI (FastAPI) we do not run a HostAgent
directly; instead we connect to a separate HTTP service.  This keeps the
concerns separated: the HostAgent server is free to run in its own process
and manage connections to remote agents, while the UI simply forwards
messages and form submissions.

The bridge reads configuration from environment variables so it can be
configured without code changes.  If no configuration is provided, sensible
defaults are used:

``HOST_URL``
    Base URL of the HostAgent server.  Defaults to ``http://127.0.0.1:8010``.
``HOST_SEND_PATH``
    Path on the HostAgent server that accepts messages.  Defaults to
    ``/api/host/run``.
``HOST_SUBMIT_PATH``
    Path on the HostAgent server that accepts form or option submissions.
    Defaults to ``/api/host/submit``.
``HOST_CARD_PATH``
    Path on the HostAgent server to retrieve the AgentCard.  Defaults to
    ``/card``.

Example usage::

    from host import HostBridge
    bridge = HostBridge()
    reply = await bridge.send_message("Xin chào")
    print(reply)

When the UI receives a request on ``/api/message`` or ``/api/submit``,
``routes.py`` uses this ``HostBridge`` to forward the payload to the
configured HostAgent server.  The bridge returns whatever JSON is returned
from the HostAgent.  Any errors are propagated up to the caller.
"""

import os
from typing import Any, Dict, Optional

import httpx


class HostBridge:
    """Proxy between the FastAPI UI and a remote HostAgent service.

    The bridge hides the details of making HTTP calls to the HostAgent
    service.  It exposes simple coroutine methods that mirror the calls
    expected by the frontend: listing remote agents, sending chat
    messages, and submitting form or option payloads.
    """

    def __init__(self) -> None:
        # Read configuration from environment variables with sensible defaults.
        self.host_url: str = os.getenv("HOST_URL", "http://127.0.0.1:8010")
        self.send_path: str = os.getenv("HOST_SEND_PATH", "/api/host/run")
        self.submit_path: str = os.getenv("HOST_SUBMIT_PATH", "/api/host/submit")
        self.card_path: str = os.getenv("HOST_CARD_PATH", "/card")

    async def list_remote_agents(self) -> Any:
        """Return the AgentCard of the HostAgent.

        The returned JSON should contain information about the host agent and
        any registered remote agents.  This method simply performs an HTTP
        GET to the ``/card`` endpoint on the HostAgent server and returns
        whatever JSON is provided.
        """
        url = self.host_url.rstrip("/") + self.card_path
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def send_message(
        self,
        message: str,
        patient: Optional[Dict[str, Any]] = None,
        mode: Optional[str] = None,
    ) -> Any:
        """Send a chat message to the HostAgent and return its response.

        Parameters
        ----------
        message:
            The raw text from the user.  This is forwarded to the
            HostAgent server as-is under the ``text`` key.
        patient:
            Optional patient metadata.  This parameter is ignored by the
            HostAgent proxy; if needed, the host service should be
            modified to accept additional fields.  Included here for
            compatibility with the ChatIn model in routes.py.
        mode:
            Optional routing mode ("orchestrate", "diagnose", etc.).  Like
            ``patient``, this parameter is ignored by the proxy but left in
            place to avoid breaking the API signature expected by the UI.

        Returns
        -------
        Any
            JSON data returned by the HostAgent server.  Typically this
            will be a dict with keys ``type`` and ``content`` or other
            structured fields understood by the front‑end.
        """
        payload: Dict[str, Any] = {"text": message}
        # We intentionally ignore patient and mode when calling the host.  If
        # the host service needs these, you can include them in the payload
        # here, for example: payload.update({"patient": patient, "mode": mode}).
        url = self.host_url.rstrip("/") + self.send_path
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            # Raise for HTTP errors so FastAPI returns 5xx to the client.
            response.raise_for_status()
            return response.json()

    async def send_task(self, agent: str, payload: Dict[str, Any]) -> Any:
        """Submit a form or option selection to the HostAgent.

        This method sends a JSON payload to the HostAgent service with the
        given ``kind`` (agent identifier) and ``values`` (arbitrary data
        dictionary).  The HostAgent decides how to interpret this based on
        ``kind``.  For example, if ``agent`` is "cost_agent", the HostAgent
        will route the payload to a cost estimation remote agent.  See
        routes.py for examples of how this is used.

        Parameters
        ----------
        agent:
            Identifier for the remote agent or task type.  The remote
            host implementation will interpret this string.
        payload:
            Arbitrary dictionary of values, typically representing form
            inputs or selected options.

        Returns
        -------
        Any
            JSON data returned by the HostAgent server after processing
            the task submission.
        """
        json_payload = {"kind": agent, "values": payload}
        url = self.host_url.rstrip("/") + self.submit_path
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=json_payload)
            response.raise_for_status()
            return response.json()


# These helper functions maintain backwards compatibility with earlier versions
# of the UI that imported ``handle_user_message`` and ``handle_submit`` directly
# from this module.  They simply forward to the appropriate methods on a
# singleton ``HostBridge`` instance.  If you are using the updated
# routes.py, these functions are not used.
_bridge = HostBridge()


async def handle_user_message(message: str):
    return await _bridge.send_message(message)


async def handle_submit(kind: str, values: Dict[str, Any]):
    return await _bridge.send_task(kind, values)
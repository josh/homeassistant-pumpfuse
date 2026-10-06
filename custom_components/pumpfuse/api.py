import re
from dataclasses import dataclass
from typing import Any, cast

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    DeviceConfig,
    HistoryEvent,
    Info,
    LastRun,
    Learn,
    Status,
    SumpStatus,
)

TIMEOUT = ClientTimeout(total=10)


class PumpFuseError(Exception):
    pass


class CannotConnect(PumpFuseError):
    pass


class InvalidResponse(PumpFuseError):
    pass


class UnsupportedModel(PumpFuseError):
    pass


def validate_host(host: str) -> str:
    host = host.strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host):
        raise ValueError("Enter an IPv4 address or hostname without a scheme or port")
    return host


@dataclass(frozen=True)
class PumpFuseIdentity:
    mac: str
    name: str
    firmware: str


@dataclass(frozen=True)
class PumpFuseState:
    firmware: str
    status: Status
    sump: SumpStatus
    learn: Learn
    history: list[HistoryEvent]
    last_run: LastRun | None


def _activity(sump: SumpStatus) -> tuple[object, ...]:
    return (
        sump["run_count_total"],
        sump["alerts"],
        sump["protection_mode"],
        sump["protection_auto_disabled"],
        sump["lockout_active"],
    )


def _needs_full_refresh(
    previous: PumpFuseState, status: Status, sump: SumpStatus
) -> bool:
    # learn and history only change after a run, an alert, a mode change, or a
    # reboot, all of which show up in the cheap status reads.
    return status["uptime"] < previous.status["uptime"] or _activity(sump) != _activity(
        previous.sump
    )


class PumpFuseClient:
    def __init__(self, session: ClientSession, host: str) -> None:
        self._session = session
        self.host = host

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"http://{self.host}/api/v1/{path}"
        try:
            async with self._session.request(
                method, url, json=body, timeout=TIMEOUT
            ) as response:
                # Validation failures come back as 400 with a plain-text reason.
                if response.status == 400:
                    reason = (await response.text()).strip()
                    raise InvalidResponse(f"{url} rejected the request: {reason}")
                response.raise_for_status()
                return await response.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise CannotConnect(f"Could not reach {url}: {err}") from err
        except ValueError as err:
            raise InvalidResponse(f"{url} did not return JSON") from err

    async def _fetch_object(
        self, path: str, required: frozenset[str]
    ) -> dict[str, Any]:
        payload = await self._request("GET", path)
        if not isinstance(payload, dict):
            raise InvalidResponse(f"{path} did not return a JSON object")
        missing = required - payload.keys()
        if missing:
            raise UnsupportedModel(f"{path} is missing {', '.join(sorted(missing))}")
        return cast(dict[str, Any], payload)

    async def fetch_info(self) -> Info:
        info = cast(Info, await self._fetch_object("info", Info.__required_keys__))
        if info["product"] != "sump":
            raise UnsupportedModel(f"The device is a {info['product']!r} monitor")
        return info

    async def _fetch_history(self) -> list[HistoryEvent]:
        payload = await self._request("GET", "sump/history")
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) and HistoryEvent.__required_keys__ <= item.keys()
            for item in payload
        ):
            raise InvalidResponse("sump/history did not return a list of events")
        return cast(list[HistoryEvent], payload)

    async def fetch_identity(self) -> PumpFuseIdentity:
        info = await self.fetch_info()
        config = cast(
            DeviceConfig,
            await self._fetch_object("config", DeviceConfig.__required_keys__),
        )
        return PumpFuseIdentity(
            mac=info["mac"].lower(),
            name=config["device_name"].strip(),
            firmware=info["firmware"],
        )

    async def fetch(self, previous: PumpFuseState | None, full: bool) -> PumpFuseState:
        # The firmware serves one request at a time, so these run in sequence.
        status = cast(
            Status, await self._fetch_object("status", Status.__required_keys__)
        )
        sump = cast(
            SumpStatus,
            await self._fetch_object("sump/status", SumpStatus.__required_keys__),
        )
        if previous is None or full or _needs_full_refresh(previous, status, sump):
            learn = cast(
                Learn, await self._fetch_object("sump/learn", Learn.__required_keys__)
            )
            history = await self._fetch_history()
        else:
            learn, history = previous.learn, previous.history
        last_run = previous.last_run if previous else None
        # The waveform only changes when a cycle completes.
        if sump["last_run_end_ms"] and (
            last_run is None or last_run["end_ms"] != sump["last_run_end_ms"]
        ):
            last_run = cast(
                LastRun,
                await self._fetch_object("sump/last-run", LastRun.__required_keys__),
            )
        return PumpFuseState(
            firmware=status["firmware"],
            status=status,
            sump=sump,
            learn=learn,
            history=history,
            last_run=last_run,
        )

    async def set_relay(self, on: bool) -> None:
        await self._request("POST", "relay", {"relay": on})

    async def set_sump_config(self, updates: dict[str, int]) -> None:
        await self._request("POST", "sump/config", updates)

    async def reset_lockout(self) -> None:
        await self._request("POST", "sump/lockout/reset")

    async def reset_stats(self) -> None:
        await self._request("POST", "sump/stats/reset")

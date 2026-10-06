from typing import Final, NotRequired, TypedDict

DOMAIN = "pumpfuse"
MANUFACTURER = "PumpFuse"
MODEL = "PF-SUMP-001"
DEFAULT_SCAN_INTERVAL = 5

# Ordered by bit position in alert_enable_mask; the first three are also the
# relay_cut_mask bits.
ALERTS: Final = (
    "power_anomaly_low",
    "power_anomaly_high",
    "long_run",
    "frequent_cycling",
    "inactivity",
)
RELAY_CUT_ALERTS: Final = ALERTS[:3]

PROTECTION_MODES: Final = ["learning", "active", "suspended", "disabled"]

EVENT_TYPES: Final = [
    "alert_fired",
    "alert_cleared",
    "power_outage",
    "protection_auto_disabled",
    "mode_change",
    "lockout_reset",
    "device_boot",
]


class Info(TypedDict):
    product: str
    firmware: str
    mac: str


class DeviceConfig(TypedDict):
    device_name: str


class Status(TypedDict):
    firmware: str
    uptime: int
    wifi_rssi: int
    relay: bool


class SumpStatus(TypedDict):
    pump_running: bool
    current_run_s: int
    current_power_w: float
    alerts: list[str]
    protection_mode: str
    protection_auto_disabled: bool
    lockout_active: bool
    lockout_remaining_s: int
    lockout_retries_used: int
    lockout_alert: str | None
    run_count_total: int
    runs_last_24h: int
    total_runtime_s: int
    last_outage_s: int
    last_run_end_ms: int | None
    last_run_dur_s: int
    last_run_avg_w: float
    last_run_peak_w: float
    idle_w: float
    active_w: float
    on_threshold_w: float
    inter_run_gap_mean: float | None
    alert_enable_mask: int
    relay_cut_mask: int
    inactivity_alert_min: int
    anomaly_lockout_min: int
    lockout_max_retries: int


class Learn(TypedDict):
    mode: str
    cycle_count: int
    wattage_mean: float
    runtime_mean: float


class LastRun(TypedDict):
    start_ms: int | None
    end_ms: int | None
    dur_s: int
    std_w: float
    samples: list[float]


class HistoryEvent(TypedDict):
    event: str
    timestamp_ms: int
    alert: NotRequired[str]

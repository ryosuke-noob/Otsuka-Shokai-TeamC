# src/sales_agent_pkg/services/constants.py

# --- Status Definitions ---
STATUS_UNANSWERED = "unanswered"
STATUS_ON_HOLD = "on_hold"
STATUS_TAKE_HOME = "take_home"
STATUS_RESOLVED = "resolved"

# --- Mappings for UI ---
JP_STATUS_MAP = {
    STATUS_UNANSWERED: "未取得",
    STATUS_ON_HOLD: "保留中",
    STATUS_TAKE_HOME: "持ち帰り",
    STATUS_RESOLVED: "聞けた",
}

# Create reverse mapping from Japanese to English status
EN_STATUS_MAP = {v: k for k, v in JP_STATUS_MAP.items()}

# Define the order of statuses in the UI dropdown
UI_STATUS_ORDER = [
    JP_STATUS_MAP[STATUS_UNANSWERED],
    JP_STATUS_MAP[STATUS_ON_HOLD],
    JP_STATUS_MAP[STATUS_TAKE_HOME],
    JP_STATUS_MAP[STATUS_RESOLVED],
]

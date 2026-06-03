import json
from pathlib import Path
from src.layout.parser import load_store_config
from src.config import STORE_CONFIG_PATH
from src.session_manager import SessionManager
from src.reid import OSNetReID
from src.event_emitter import EventEmitter

print("STORE_CONFIG_PATH =", STORE_CONFIG_PATH)
config = load_store_config(STORE_CONFIG_PATH, "ST1008")
print("Store config loaded:", config)
if config:
    print("Cameras count:", len(config.cameras))
    for cam in config.cameras:
        print(f"Cam: {cam.camera_id}, desc: {cam.description}, entry: {cam.entry_line}, exit: {cam.exit_line}")
    print("Brand zones count:", len(config.brand_zones))

session_mgr = SessionManager(store_id="ST1008")
reid = OSNetReID()

# Mock event emitter setup
print("\nInitializing EventEmitter for ST1008 CAM1...")
emitter = EventEmitter(
    store_id="ST1008",
    camera_id="CAM1",
    store_layout={},
    session_manager=session_mgr,
    reid_gallery=reid,
    fps=30.0
)
print("Emitter initialized successfully!")
print("Zones:", list(emitter.zones.keys()))
print("Entry line:", emitter.entry_line)
print("Exit line:", emitter.exit_line)
print("Billing zones:", emitter.billing_zones)
print("Queue zones:", list(emitter.queue_zones.keys()))

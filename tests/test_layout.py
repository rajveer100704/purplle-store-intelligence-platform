"""
tests/test_layout.py – Unit tests for StoreConfig layout configuration and parser.
"""

import json
from pathlib import Path
import pytest
from src.layout.parser import load_store_config, StoreConfig, ZoneConfig, CameraConfig


def test_layout_parser_mock(tmp_path):
    config_data = {
        "stores": {
            "ST1008": {
                "store_name": "Brigade_Bangalore",
                "city": "Bangalore",
                "store_open_hour": 10,
                "cameras": [
                    {
                        "camera_id": "CAM1",
                        "description": "Entry",
                        "frame_size": [1920, 1080],
                        "entry_line": [[50, 200], [50, 880]],
                        "exit_line": [[50, 200], [50, 880]]
                    }
                ],
                "billing_zone": {
                    "zone_id": "CASH_COUNTER",
                    "type": "billing",
                    "polygon": [[0.82, 0.05], [0.97, 0.05], [0.97, 0.65], [0.82, 0.65]]
                },
                "brand_zones": [
                    {
                        "zone_id": "LAKME",
                        "brand": "Lakme",
                        "wall": "bottom",
                        "position": 2,
                        "polygon": [[0.28, 0.88], [0.37, 0.88], [0.37, 0.98], [0.28, 0.98]]
                    }
                ]
            }
        }
    }
    
    cfg_file = tmp_path / "store_config.json"
    cfg_file.write_text(json.dumps(config_data))
    
    cfg = load_store_config(cfg_file, "ST1008")
    assert cfg is not None
    assert cfg.store_name == "Brigade_Bangalore"
    assert cfg.city == "Bangalore"
    assert cfg.store_open_hour == 10
    
    cam = cfg.get_camera("CAM1")
    assert cam is not None
    assert cam.description == "Entry"
    assert cam.frame_size == (1920, 1080)
    assert cam.pixel_entry_line() == [[50, 200], [50, 880]]
    assert cam.pixel_exit_line() == [[50, 200], [50, 880]]
    
    assert cfg.all_zone_ids() == ["LAKME", "CASH_COUNTER"]
    assert cfg.brand_zone_ids() == ["LAKME"]
    assert cfg.zone_brand_map() == {"LAKME": "Lakme"}
    
    # Scale to pixels
    pixel_zones = cfg.pixel_zones(100, 100)
    assert "LAKME" in pixel_zones
    assert "CASH_COUNTER" in pixel_zones
    
    # Check legacy convert
    legacy = cfg.to_legacy_layout()
    assert "stores" in legacy
    assert "ST1008" in legacy["stores"]
    assert len(legacy["stores"]["ST1008"]["zones"]) == 2

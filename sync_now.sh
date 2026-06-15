#!/bin/bash
# Run the schedule sync immediately.
cd "$(dirname "$0")"
.venv/bin/python sync_schedule.py

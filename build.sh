#!/bin/bash
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
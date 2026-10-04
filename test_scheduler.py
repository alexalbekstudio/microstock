# test_scheduler.py
import logging
logging.basicConfig(level=logging.INFO)

import os
os.environ["WERKZEUG_RUN_MAIN"] = "true"  # zaobiđi debug proveru

from flask import Flask
from scheduler import init_scheduler, _run_nbs_rates

app = Flask(__name__)
app.debug = False

init_scheduler(app)

# Odmah izvrši NBS posao (kao da je 08:05)
_run_nbs_rates(app)

print("Test završen — pogledaj log ispod.")
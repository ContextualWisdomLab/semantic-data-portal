import json
from copy import deepcopy
from pathlib import Path
from time import time

import jwt
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import sdp.catalog as app_catalog
import sdp.domain as app_domain
import sdp.evidence as app_evidence
import sdp.observability as app_observability
import sdp_core
from sdp.api import app
from sdp.connectors import get_source_connector
from sdp.demo_smoke import smoke_summary
from sdp.policy import evaluate


client = TestClient(app)
